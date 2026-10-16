"""Offline tests: synthetic pixels, mocked OCR/HTTP/portal, no windows or audio."""
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_runtime = tempfile.TemporaryDirectory(prefix='tradutor-test-')
os.environ['XDG_STATE_HOME'] = _runtime.name
os.environ['TG_CONFIG'] = str(Path(_runtime.name) / 'absent.toml')

from PIL import Image, ImageDraw
import core
from core import Pilot, Cancelled, MODEL
from frames import FrameGate, frame_quality
from settings import CONFIG, STATE_DIR, validate, write_private


def fixture():
    image = Image.new('RGB', (500, 100), 'white')
    ImageDraw.Draw(image).text((20, 20), 'Our shields took damage.', fill='black')
    return image


class FakeOpener:
    def __init__(self, text='Nossos escudos sofreram danos.', reason='stop', error=None):
        self.text, self.reason, self.error = text, reason, error
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append(request)
        assert request.full_url == 'http://127.0.0.1:11434/api/generate'
        if self.error:
            return io.BytesIO((json.dumps({'error': self.error}) + '\n').encode())
        rows = [{'response': self.text}, {'done': True, 'done_reason': self.reason, 'total_duration': 1000000000}]
        return io.BytesIO(('\n'.join(json.dumps(r) for r in rows) + '\n').encode())


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.p = Pilot(Path(self.temp.name) / 'cache')
        self.p.opener = FakeOpener()
        self.p.api = Mock(side_effect=lambda endpoint, *a, **k: {
            'tags': {'models': [{'name': MODEL, 'digest': 'synthetic-digest'}]},
            'ps': {'models': []}, 'generate': {},
        }[endpoint])
        self.p.resource_pressure = Mock(return_value=None)

    def test_translation_is_local_general_and_releases_own_alias(self):
        text, cached, evidence = self.p.translate('Our shields took damage.', [])
        self.assertEqual(text, 'Nossos escudos sofreram danos.')
        self.assertFalse(cached)
        self.assertEqual(evidence['glossary'], {})
        body = json.loads(self.p.opener.calls[0].data)
        self.assertEqual(body['model'], MODEL)
        self.assertEqual(body['keep_alive'], 0)
        self.assertEqual(body['options']['num_ctx'], 4096)
        self.p.api.assert_any_call('generate', {'model': MODEL, 'keep_alive': 0}, timeout=60)
        self.assertFalse(self.p.owns_model)

    def test_repeat_is_cached_and_does_not_load(self):
        self.p.translate('Our shields took damage.', [])
        self.p.opener.calls.clear()
        self.p.api.reset_mock()
        self.assertTrue(self.p.translate('Our shields took damage.', [])[1])
        self.assertEqual(self.p.opener.calls, [])
        self.assertEqual([c.args[0] for c in self.p.api.call_args_list], ['tags'])

    def test_busy_ollama_is_not_evicted(self):
        for busy in ['another-model', MODEL]:
            self.p.api = Mock(return_value={'models': [{'name': busy}]})
            with self.assertRaisesRegex(RuntimeError, 'ativo'):
                self.p.guard()
            self.assertEqual([c.args[0] for c in self.p.api.call_args_list], ['ps'])
        self.assertEqual(self.p.opener.calls, [])

    def test_pressure_stops_before_loading(self):
        self.p.resource_pressure.return_value = 'Memória insuficiente'
        with self.assertRaisesRegex(RuntimeError, 'Memória insuficiente'):
            self.p.translate('Hello', [])
        self.assertEqual(self.p.opener.calls, [])

    def test_incomplete_or_failed_translation_never_cached(self):
        for opener in [FakeOpener(reason='length'), FakeOpener(error='synthetic failure'), FakeOpener(text='')]:
            self.p.opener = opener
            with self.assertRaises(RuntimeError):
                self.p.translate('Hello', [])
            self.assertEqual(list(self.p.cache_dir.glob('*.json')), [])
            self.assertFalse(self.p.owns_model)

    def test_cancellation_prevents_io(self):
        self.p.cancel()
        with self.assertRaises(Cancelled):
            self.p.translate('Hello', [])
        self.p.api.assert_not_called()

    def test_eve_glossary_is_opt_in_and_alias_restoration_declared(self):
        self.p.neutral = False
        self.p.opener = FakeOpener(text='Ordem de São Tetrimon')
        text, _, evidence = self.p.translate('Order of St. Tetrimon', ['Order of St. Tetrimon'])
        self.assertEqual(text, 'Order of St. Tetrimon')
        self.assertEqual(evidence['raw_translation'], 'Ordem de São Tetrimon')
        self.assertTrue(evidence['restored_aliases'])
        self.assertEqual(evidence['glossary'], core.GLOSSARY)

    def test_names_are_enforced_without_substring_double_count(self):
        self.assertEqual(Pilot.name_counts('Blood Raiders and Blood Raider', ['Blood Raider', 'Blood Raiders']), {'Blood Raiders': 1, 'Blood Raider': 1})
        self.p.opener = FakeOpener(text='Um nome diferente')
        with self.assertRaisesRegex(RuntimeError, 'nomes'):
            self.p.translate('Blood Raiders', ['Blood Raiders'])
        self.assertEqual(list(self.p.cache_dir.glob('*.json')), [])

    def test_cache_count_and_permissions(self):
        with patch.dict(CONFIG, cache_entries=3):
            for i in range(12):
                self.p.write_cache(str(i), {'text': 'synthetic'})
        entries = list(self.p.cache_dir.glob('*.json'))
        self.assertEqual(len(entries), 3)
        self.assertEqual(stat.S_IMODE(self.p.cache_dir.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in entries))

    def test_black_or_uniform_rejected_before_tesseract(self):
        with patch('core.subprocess.Popen') as process:
            for color in ['black', 'white']:
                with self.assertRaises(ValueError):
                    self.p.ocr(Image.new('RGB', (300, 100), color))
            process.assert_not_called()

    def test_synthetic_ocr_stdin_and_cache_with_mocked_binary(self):
        proc = Mock()
        proc.communicate.return_value = (b'Our shields took damage.', b'')
        proc.returncode = 0
        proc.poll.return_value = 0
        with patch('core.subprocess.check_output', return_value='tesseract fake\n'), patch('core.subprocess.Popen', return_value=proc) as spawn:
            self.assertFalse(self.p.ocr(fixture())[1])
            self.assertTrue(self.p.ocr(fixture())[1])
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(spawn.call_args.args[0][:3], ['tesseract', 'stdin', 'stdout'])
            self.assertTrue(proc.communicate.call_args.kwargs['input'].startswith(b'\x89PNG'))


class FrameAndStorageTests(unittest.TestCase):
    def test_gate_emits_once_after_stable_frame(self):
        gate = FrameGate()
        image = fixture()
        self.assertIsNone(gate.offer(image))
        self.assertIsNotNone(gate.offer(image))
        for _ in range(100):
            self.assertIsNone(gate.offer(image))
        changed = Image.new('RGB', image.size, 'black')
        self.assertIsNone(gate.offer(changed))
        self.assertIsNotNone(gate.offer(changed))

    def test_frame_quality(self):
        self.assertTrue(frame_quality(Image.new('RGB', (20, 20), 'black'))['black'])
        self.assertTrue(frame_quality(Image.new('RGB', (20, 20), 'white'))['uniform'])
        self.assertFalse(frame_quality(fixture())['uniform'])

    def test_private_atomic_unicode_and_no_tmp_left(self):
        path = STATE_DIR / 'test.json'
        write_private(path, {'text': 'Olá'})
        self.assertEqual(json.loads(path.read_text())['text'], 'Olá')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_config_rejects_external_models_and_invalid_values(self):
        for key, value in [('model', 'remote:cloud'), ('context', 'unknown'), ('cache_entries', 0), ('cache_entries', True)]:
            with self.assertRaises(ValueError):
                validate({**CONFIG, key: value})

    def test_portal_history_is_bounded_without_opening_dbus(self):
        from collections import deque
        import portal
        # Bypass the constructor, which obtains a real session bus.
        capture = object.__new__(portal.PortalCapture)
        capture.events = deque(maxlen=128)
        with patch('portal.write_private') as write:
            for i in range(300):
                capture.record('synthetic', {'index': i})
            self.assertEqual(len(capture.events), 128)
            self.assertEqual(capture.events[0]['details']['index'], 172)
            self.assertEqual(len(write.call_args.args[1]), 128)

    def test_gstreamer_stride_conversion_uses_only_synthetic_video(self):
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        from portal import PortalCapture
        Gst.init(None)
        pipeline = Gst.parse_launch('videotestsrc num-buffers=1 ! video/x-raw,format=RGB,width=17,height=10 ! appsink name=test sync=false')
        try:
            pipeline.set_state(Gst.State.PLAYING)
            sample = pipeline.get_by_name('test').emit('try-pull-sample', Gst.SECOND * 2)
            self.assertIsNotNone(sample)
            self.assertEqual(PortalCapture.sample_image(sample).size, (17, 10))
        finally:
            pipeline.set_state(Gst.State.NULL)

    def test_portal_refuses_monitor_or_multiple_streams_before_dbus(self):
        from portal import PortalCapture
        capture = object.__new__(PortalCapture)
        capture.bus = Mock()
        for streams in [[], [(1, {'source_type': 1})], [(1, {'source_type': 2}), (2, {'source_type': 2})]]:
            with self.assertRaises(RuntimeError):
                capture._started({'streams': streams})
        capture.bus.call_with_unix_fd_list_sync.assert_not_called()

    def test_portal_requests_only_one_window_without_persistence(self):
        from portal import PortalCapture
        capture = object.__new__(PortalCapture)
        capture.bus = Mock()
        capture._request = Mock()
        capture._created({'session_handle': '/test/synthetic'})
        args = capture._request.call_args.args
        self.assertEqual(args[0], 'SelectSources')
        self.assertEqual({k: v.unpack() for k, v in args[2].items()}, {
            'types': 2, 'multiple': False, 'cursor_mode': 1, 'persist_mode': 0})

    def test_portal_cancellation_does_not_retry(self):
        from portal import PortalCapture, PATH
        from gi.repository import GLib
        capture = object.__new__(PortalCapture)
        capture.bus = Mock()
        capture.bus.get_unique_name.return_value = ':1.2'
        capture.closed = False
        capture.record = Mock()
        capture.fail = Mock()
        success = Mock()
        capture._request('CreateSession', lambda opts: GLib.Variant('(a{sv})', (opts,)), {}, success)
        callback = capture.bus.signal_subscribe.call_args.args[6]
        callback(None, None, None, None, None, GLib.Variant('(ua{sv})', (1, {})), None)
        success.assert_not_called()
        capture.fail.assert_called_once()
        self.assertEqual(capture.bus.call.call_count, 1)

    def test_privacy_ignore_patterns(self):
        names = ['capture.png', 'sample.wav', 'recognized.json', 'recognized.txt', 'captured.csv', 'model.gguf', '.env', '.git-credentials', 'private.key', 'voices/a.flac', 'text-cache/private.json', 'config.toml']
        result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin'], cwd=ROOT,
                                input='\n'.join(names) + '\n', text=True, capture_output=True)
        if result.returncode == 128:
            self.skipTest('Inicialize o repositório Git para verificar seus padrões de exclusão.')
        self.assertEqual(set(result.stdout.splitlines()), set(names))


if __name__ == '__main__':
    unittest.main()
