"""Blitting, so dragging a slider does not redraw the whole window.

Measured on a 20x20x4x4000 A-scan file under Agg: a full ``canvas.draw()`` costs
56 ms for a waveform and 78 ms for an image -- 13 to 18 frames per second while
a slider is being dragged.  Restoring a cached background and redrawing only the
artists that moved costs 16 ms, which is about 60 fps.

The mechanism is matplotlib's standard one.  Artists that move are marked
``animated``, which excludes them from ordinary draws; the background is
captured once after such a draw, and each update restores it, draws those
artists, and blits.  A ``draw_event`` handler re-captures the background
whenever something forces a full redraw, which is also how window resizes are
picked up.

The trap that comes with it: an ``animated`` artist is skipped by *every*
ordinary draw, including the one inside ``savefig``, so a saved figure would
come out missing its data.  Use :meth:`BlitManager.static` around anything that
renders the figure by a route other than this class.
"""

import contextlib

__all__ = ["BlitManager"]


class BlitManager(object):
    """Tracks the animated artists of one figure and blits them on demand."""

    def __init__(self, figure):
        self.figure = figure
        self.artists = []
        self.background = None
        self.enabled = True
        self._connection = figure.canvas.mpl_connect("draw_event", self._on_draw)

    # -- registration ------------------------------------------------------

    def register(self, *artists):
        """Mark *artists* animated and take responsibility for drawing them."""
        for artist in artists:
            if artist is None or artist in self.artists:
                continue
            artist.set_animated(True)
            self.artists.append(artist)

    def clear(self):
        """Forget every artist, leaving them to be drawn normally again."""
        for artist in self.artists:
            try:
                artist.set_animated(False)
            except Exception:
                pass
        self.artists = []

    def reset(self, artists):
        """Replace the registered set (the controls are rebuilt on occasion)."""
        self.clear()
        self.register(*artists)
        self.invalidate()

    def invalidate(self):
        """Drop the cached background; the next update does a full draw."""
        self.background = None

    # -- drawing -----------------------------------------------------------

    def _on_draw(self, _event):
        canvas = self.figure.canvas
        try:
            self.background = canvas.copy_from_bbox(self.figure.bbox)
        except Exception:
            # A backend without background caching: blitting is simply off.
            self.enabled = False
            self.background = None
            return
        self._draw_animated()

    def _draw_animated(self):
        for artist in self.artists:
            if artist.get_visible():
                try:
                    artist.axes.draw_artist(artist)
                except Exception:
                    pass

    def update(self):
        """Blit the animated artists, or fall back to a full redraw.

        Returns True if the fast path was taken.
        """
        canvas = self.figure.canvas
        if not self.enabled or self.background is None:
            canvas.draw_idle()
            return False
        try:
            canvas.restore_region(self.background)
            self._draw_animated()
            canvas.blit(self.figure.bbox)
            canvas.flush_events()
        except Exception:
            self.enabled = False
            canvas.draw_idle()
            return False
        return True

    @contextlib.contextmanager
    def static(self):
        """Temporarily un-animate every artist, for savefig and friends.

        Without this, a saved figure is missing exactly the parts that move --
        the trace, the image, the slider handles -- because ordinary draws skip
        animated artists.
        """
        animated = [artist for artist in self.artists if artist.get_animated()]
        for artist in animated:
            artist.set_animated(False)
        try:
            yield
        finally:
            for artist in animated:
                artist.set_animated(True)
            self.invalidate()
