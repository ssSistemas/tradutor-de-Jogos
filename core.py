"""Local image import -> OCR -> translation. No screen/audio capture or playback."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.request

from PIL import Image
from frames import frame_quality

from settings import STATE_DIR as ROOT, CONFIG, write_private
MODEL = CONFIG['model']
PROMPT_VERSION = 'translategemma-ptbr-semantic-v3'
GLOSSARY = {'Capsuleers': 'Capsuleiros', 'capsuleers': 'capsuleiros',
            'attack battlecruiser': 'cruzador de batalha de ataque',
            'hacking': 'invasão de sistemas'}
DEFAULT_NAMES = ['Blood Raiders', 'Blood Raider', 'Order of St. Tetrimon',
                 'Crimson Harvest', 'New Eden', 'Pochven', 'Amarr', 'Akoman',
                 'EVE Online']
NAME_ALIASES = {'Ordem de São Tetrimon': 'Order of St. Tetrimon',
                'Ordem de St. Tetrimon': 'Order of St. Tetrimon'}


if CONFIG['context'] != 'eve':
    DEFAULT_NAMES = []


class Cancelled(Exception):
    pass


class Pilot:
    def __init__(self, cache_dir=None, *, neutral=None):
        self.cancelled = threading.Event()
        self.cache_dir = Path(cache_dir or ROOT / 'text-cache')
        self.cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.owns_model = False
        self.neutral = CONFIG['context'] != 'eve' if neutral is None else neutral

    def cancel(self):
        self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled('Operação cancelada. Nenhuma tradução parcial foi guardada.')

    def api(self, endpoint, body=None, timeout=30):
        req = urllib.request.Request('http://127.0.0.1:11434/api/' + endpoint,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=timeout) as response:
            return json.load(response)

    def release(self):
        if self.owns_model:
            # This alias belongs only to this pilot. Never unload other models.
            self.api('generate', {'model': MODEL, 'keep_alive': 0}, timeout=60)
            self.owns_model = False

    def guard(self):
        active = self.api('ps').get('models', [])
        if active:
            raise RuntimeError('Há modelo(s) local(is) ativo(s). Aguarde a outra sessão terminar; nada foi descarregado.')
        if not active:
            self.owns_model = False
        installed = self.api('tags').get('models', [])
        model = next((m for m in installed if m.get('name') == MODEL), None)
        if not model:
            raise RuntimeError('Modelo do piloto ausente. Consulte README.md.')
        reason = self.resource_pressure()
        if reason:
            self.release()
            raise RuntimeError(reason)
        return model['digest']

    def resource_pressure(self):
        """Conservative policy for the tested NVIDIA machine, not model requirements."""
        available = next((int(s.split()[1]) for s in Path('/proc/meminfo').read_text().splitlines()
                          if s.startswith('MemAvailable:')), 0)
        minimum_ram = CONFIG['min_available_ram_gib']
        if available < minimum_ram * 1024 * 1024:
            return f'Aguardando memória: menos de {minimum_ram} GiB de RAM disponíveis. Modelo do piloto pausado.'
        try:
            free = int(subprocess.check_output(['nvidia-smi', '--query-gpu=memory.free',
                      '--format=csv,noheader,nounits'], timeout=2, text=True).splitlines()[0])
            minimum_vram = CONFIG['min_free_vram_mib']
            if free < minimum_vram:
                return f'Aguardando VRAM: menos de {minimum_vram} MiB livres. Modelo do piloto pausado.'
        except (FileNotFoundError, subprocess.SubprocessError, ValueError):
            return 'Não foi possível verificar a VRAM. Modelo do piloto pausado.'
        return None

    @staticmethod
    def normalize(text):
        paragraphs = re.split(r'\n\s*\n', text.strip())
        return '\n\n'.join(' '.join(p.split()) for p in paragraphs if p.strip())

    @staticmethod
    def name_counts(text, names):
        relevant = sorted(set(n.strip() for n in names if n.strip()), key=len, reverse=True)
        if not relevant:
            return {}
        pattern = '|'.join(re.escape(n) for n in relevant)
        matches = re.findall(r'(?<!\w)(?:' + pattern + r')(?!\w)', text)
        return {n: matches.count(n) for n in relevant if n in matches}

    def read_cache(self, key):
        p = self.cache_dir / (key + '.json')
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None

    def write_cache(self, key, value):
        self.check()
        p = self.cache_dir / (key + '.json')
        write_private(p, value)
        entries = sorted(self.cache_dir.glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True)
        for expired in entries[CONFIG['cache_entries']:]:
            expired.unlink(missing_ok=True)

    def ocr(self, image):
        self.check()
        if isinstance(image, Image.Image):
            quality = frame_quality(image)
            if quality['black'] or quality['uniform']:
                raise ValueError('Quadro preto ou uniforme: OCR não iniciado.')
            if image.width * image.height > 24_000_000:
                raise ValueError('Área grande demais; escolha só a área do texto.')
            memory = io.BytesIO()
            image.save(memory, format='PNG')
            payload = memory.getvalue()
        else:
            image = Path(image).resolve(strict=True)
            if image.stat().st_size > 25 * 1024 * 1024:
                raise ValueError('Imagem maior que 25 MB. Escolha um recorte menor.')
            payload = image.read_bytes()
        if len(payload) > 25 * 1024 * 1024:
            raise ValueError('Imagem maior que 25 MB. Escolha um recorte menor.')
        with Image.open(io.BytesIO(payload)) as im:
            if im.width * im.height > 24_000_000:
                raise ValueError('Imagem grande demais. Escolha só a área do texto.')
            im.verify()
        image_hash = hashlib.sha256(payload).hexdigest()
        version = subprocess.check_output(['tesseract', '--version'], text=True).splitlines()[0]
        key = hashlib.sha256(('ocr-v1|' + version + '|' + image_hash).encode()).hexdigest()
        cached = self.read_cache(key)
        if cached:
            return cached['text'], True
        proc = subprocess.Popen(['tesseract', 'stdin', 'stdout', '-l', 'eng'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={**os.environ, 'OMP_THREAD_LIMIT': '4'})
        deadline = time.monotonic() + 45
        pending_input = payload
        try:
            while True:
                self.check()
                if time.monotonic() > deadline:
                    raise TimeoutError('OCR demorou mais de 45 segundos; escolha um recorte menor.')
                try:
                    out, err = proc.communicate(input=pending_input, timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    pending_input = None
                    continue
            if proc.returncode:
                raise RuntimeError('OCR falhou: ' + err.decode(errors='replace')[-300:])
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        text = self.normalize(out.decode('utf-8', errors='replace'))
        if not text or not any(c.isalpha() for c in text):
            raise ValueError('Não encontrei texto. Escolha um recorte mais nítido e próximo.')
        if len(text) > 4000:
            raise ValueError('Mais de 4000 caracteres reconhecidos. Escolha um recorte menor.')
        self.write_cache(key, {'text': text, 'image_hash': image_hash, 'ocr': version})
        return text, False

    def translate(self, text, names, progress=None):
        self.check()
        text = self.normalize(text)
        if len(text) > 4000:
            raise ValueError('Texto maior que 4000 caracteres.')
        # Reading installed model metadata does not load or evict a model.
        installed = self.api('tags').get('models', [])
        entry = next((m for m in installed if m.get('name') == MODEL), None)
        if not entry:
            raise RuntimeError('Modelo do piloto ausente. Consulte README.md.')
        key = hashlib.sha256(json.dumps([PROMPT_VERSION, entry['digest'], text, sorted(names), self.neutral],
                                       ensure_ascii=False).encode()).hexdigest()
        cached = self.read_cache(key)
        if cached:
            return cached['translation'], True, cached
        expected_names = self.name_counts(text, names)
        glossary = {} if self.neutral else GLOSSARY
        prompt = ('You are a professional English (en) to Brazilian Portuguese (pt-BR) translator. '
                  'Your goal is to accurately convey the meaning and nuances of the original English text '
                  'while adhering to Brazilian Portuguese grammar, vocabulary, and cultural sensitivities.\n'
                  'Produce only the Brazilian Portuguese translation, without any additional explanations '
                  'or commentary. Keep these proper names exactly as written: ' + '; '.join(expected_names) + '. '
                  'Use this glossary: ' + '; '.join(k + '=' + v for k, v in glossary.items()) + '. '
                  'Please translate the following English text into Brazilian Portuguese:\n\n\n' + text)
        self.guard()
        self.check()
        request = urllib.request.Request('http://127.0.0.1:11434/api/generate',
            data=json.dumps({'model': MODEL, 'prompt': prompt, 'stream': True, 'keep_alive': 0,
                             'options': {'num_ctx': 4096,
                                         'num_predict': 1800,
                                         'temperature': 0}}).encode(),
            headers={'Content-Type': 'application/json'})
        self.owns_model = True
        chunks, final = [], None
        try:
            with self.opener.open(request, timeout=90) as response:
                for line in response:
                    self.check()
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get('error'):
                        raise RuntimeError(item['error'])
                    chunks.append(item.get('response', ''))
                    if progress:
                        progress(len(''.join(chunks)))
                    if item.get('done'):
                        final = item
                        break
            self.check()
            if not final or final.get('done_reason') == 'length':
                raise RuntimeError('Resposta incompleta. Escolha um recorte menor; não foi guardada no cache.')
            raw = ''.join(chunks).strip()
            translated = raw
            restored_aliases = []
            for alias, original in NAME_ALIASES.items():
                if original in expected_names and alias in translated:
                    restored_aliases.append({'from': alias, 'to': original, 'count': translated.count(alias)})
                    translated = translated.replace(alias, original)
            if self.name_counts(translated, names) != expected_names:
                raise RuntimeError('O tradutor não preservou todos os nomes. Nada foi salvo; tente um recorte menor.')
            if not translated:
                raise RuntimeError('Tradução inválida. Nada foi guardado no cache.')
            evidence = {'translation': translated, 'input': text, 'raw_translation': raw,
                        'names': expected_names, 'restored_aliases': restored_aliases,
                        'glossary': glossary, 'neutral': self.neutral, 'model': MODEL,
                        'digest': entry['digest'], 'prompt_version': PROMPT_VERSION,
                        'model_seconds': final.get('total_duration', 0) / 1e9,
                        'load_seconds': final.get('load_duration', 0) / 1e9,
                        'prompt_seconds': final.get('prompt_eval_duration', 0) / 1e9,
                        'generation_seconds': final.get('eval_duration', 0) / 1e9,
                        'context_requested': 4096,
                        'output_tokens': final.get('eval_count')}
            self.write_cache(key, evidence)
            return translated, False, evidence
        finally:
            self.release()

    def run(self, image, names=None, status=None):
        started = time.monotonic()
        if status:
            status('Lendo o texto da imagem…')
        text, ocr_cached = self.ocr(image)
        ocr_time = time.monotonic() - started
        self.check()
        if status:
            status('Traduzindo localmente… Cancelar permanece disponível.')
        tick = time.monotonic()
        translated, cached, evidence = self.translate(text, names if names is not None else ([] if self.neutral else DEFAULT_NAMES))
        return {'input': text, 'translation': translated, 'model': MODEL,
                'ocr_cached': ocr_cached, 'translation_cached': cached,
                'ocr_seconds': ocr_time, 'translation_seconds': time.monotonic() - tick,
                'total_seconds': time.monotonic() - started,
                'evidence': evidence}
