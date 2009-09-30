import unittest
from geoscript import geom, proj, feature

class LayerTest:

  def testCount(self):
    assert 49, self.l.count()

  def testCRS(self):
    cs = self.l.crs
    assert cs
    assert 'EPSG:4326', proj.srs(cs)

  def testBounds(self):
    b = self.l.bounds()
    assert -124, int(b.getMinX())
    assert 24, int(b.getMinY())
    assert -66, int(b.getMaxX())
    assert 49, int(b.getMaxY())

  def testFeatures(self):
    count = 0
    for f in self.l.features():
      assert f
      assert f.get('STATE_NAME')
      count += 1

    assert 49, count

  def testFeaturesFilter(self):
     features = [f for f in self.l.features("STATE_ABBR EQ 'TX'")]
     assert 1, len(features)
     assert 'Texas', features[0].get('STATE_NAME')

  def testReproject(self):
     rgeoms = [proj.transform(f.geom(),self.l.crs,'epsg:3005') for f in self.l.features()]
     i = 0
     for f in self.l.reproject('epsg:3005'):
        assert str(rgeoms[i].coordinate), str(f.geom().coordinate)
        i += 1
