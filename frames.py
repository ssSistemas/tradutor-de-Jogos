"""Bounded, stable-change detection. Synthetic frames can test it without capture."""
from PIL import ImageChops, ImageStat


def frame_quality(image):
    thumb = image.convert('L').resize((256, 144))
    stats = ImageStat.Stat(thumb)
    low, high = thumb.getextrema()
    return {'mean_luma': round(stats.mean[0], 3), 'stddev_luma': round(stats.stddev[0], 3),
            'min_luma': low, 'max_luma': high,
            'black': high <= 12 or (stats.mean[0] < 2 and stats.stddev[0] < 3),
            'uniform': stats.stddev[0] < 1.0}


class FrameGate:
    def __init__(self):
        self.anchor = None
        self.generation = 0
        self.emitted = -1

    def offer(self, image):
        thumb = image.convert('L').resize((240, 90))
        changed = self.anchor is None
        if self.anchor is not None:
            diff = ImageChops.difference(thumb, self.anchor)
            histogram = diff.histogram()
            changed = sum(histogram[20:]) / (240 * 90) > 0.003
        if changed:
            self.anchor = thumb
            self.generation += 1
            return None
        if self.emitted == self.generation:
            return None
        self.emitted = self.generation
        return self.generation, image.copy()
