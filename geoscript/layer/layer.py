"""
The :mod:`layer` module provides data access and manipulation.
"""
import sys

from java import io
from java import net
from geoscript import geom, proj, feature
from org.geotools.data import DefaultQuery, Query, Transaction
from org.geotools.feature import FeatureCollections
from org.geotools.filter.text.cql2 import CQL
from org.opengis.filter import Filter

class Layer(object):
  """
  A dataset of a particular format. A layer is complex of a :class:`geoscript.feature.Feature` objects.
  """

  def __init__(self, fs=None, name='layer'):
    if self.__class__ == Layer and not fs:
      import memory
      mem = memory.MemoryLayer(name,[('geom',geom.Geometry)])
      self.fs = mem.fs
      self.schema = mem.schema
    else:
      if not fs:
        raise Exception('Layer requires a feature source.')

      self.fs = fs
      self.schema = feature.Schema(ft=fs.schema) 

    # we keep a crs local to allow the native crs to be overriden, or to 
    # provide a crs for layers that don't have one specified
    self._proj = None

  def getname(self):
    return self.fs.name.localPart

  name = property(getname)
  """
  The name of the layer.
  """

  def getproj(self):
    if self._proj:
      return self._proj
    else:
      crs = self.fs.schema.coordinateReferenceSystem
      if crs:
        return proj.Projection(crs)

  def setproj(self, value):
    self._proj = proj.Projection(value) 

  proj = property(getproj, setproj)
  """
  The :class:`geoscript.proj.Projection` of the layer. In cases where the projection of a layer is unkown this attribute has the value ``None``.

  >>> import proj
  >>> l = Layer()
  >>> l.proj
  None
  >>> l.proj = proj.Projection('epsg:4326')
  >>> l.proj.id
  EPSG:4326
  """

  def count(self, filter=None):
    """
    The number of features in the layer.

    >>> l = Layer()
    >>> l.count()
    0
    >>> from geoscript import geom
    >>> l.add([geom.Point(1,2)])
    >>> l.count()
    1
    
    This method takes an option filter paramter specified as CQL:

    >>> l.add([geom.Point(3,4)])
    >>> l.count() 
    2
    >>> l.count('INTERSECTS(geom,POINT(3 4))')
    1
    """

    f = self._filter(filter)
    count = self.fs.getCount(DefaultQuery(self.name, f))
    if count == -1:
      count = 0
      # calculate manually 
      for f in self.features(filter):
        count += 1

    return count

  def bounds(self, filter=None):
    """
    The :class:`geoscript.geom.Bounds` of the layer.

    >>> l = Layer()
    >>> from geoscript import geom 
    >>> l.add([geom.Point(1.0, 2.0)])
    >>> l.add([geom.Point(3.0, 4.0)])

    >>> l.bounds()
    (1.0, 2.0, 3.0, 4.0)

    This method takes an optional filter parameter specified as CQL:

    >>> l.bounds('INTERSECTS(geom,POINT(3 4))')
    (3.0, 4.0, 3.0, 4.0)
    """

    e = self.fs.getBounds(DefaultQuery(self.name, self._filter(filter)))
    if e:
      return geom.Bounds(env=e)

  def features(self, filter=None, transform=None):
    """
    Iterates over the :class:`geoscript.feature.Feature` contained in the layer.

    >>> l = Layer()
    >>> from geoscript import geom
    >>> l.add([geom.Point(1,2)])
    >>> l.add([geom.Point(3,4)])
    >>> [ str(f.geom) for f in l.features() ]
    ['POINT (1 2)', 'POINT (3 4)']

    This method takes an optional *filter* argument specified as CQL:

    >>> [ str(f.geom) for f in l.features('INTERSECTS(geom,POINT(3 4))') ]
    ['POINT (3 4)']

    This method takes an optional *transform* argument, which is a function that
    takes a Feature instance. Each feature being iterated over is passed to the
    transform function before it is returned.

    >>> def tx (f):
    ...    f.geom = geom.Point(2*f.geom.x, 2*f.geom.y)
    >>> [str(f.geom) for f in l.features(transform=tx)]
    ['POINT (2 4)', 'POINT (6 8)']
    """

    q = DefaultQuery(self.name, self._filter(filter))
    r = self.fs.dataStore.getFeatureReader(q,Transaction.AUTO_COMMIT)
    while r.hasNext():
      f = feature.Feature(schema=self.schema, f=r.next())
      if transform:
         result  = transform(f)
         if result and isinstance(result, Feature):
           f = result

      yield f

    r.close()

  def delete(self, filter):
    """
    Deletes features from the layer which match the specified *filter*.

    >>> l = Layer()
    >>> from geoscript import geom
    >>> l.add([geom.Point(1,2)])
    >>> l.add([geom.Point(3,4)])
    >>> l.count()
    2
    >>> l.delete('INTERSECTS(geom, POINT(3 4))')
    >>> l.count()
    1
    """

    f = self._filter(filter,Filter.EXCLUDE)
    self.fs.removeFeatures(f)

  def add(self, o):
    """
    Adds a :class:`geoscript.feature.Feature` to the layer.

    >>> from geoscript import geom
    >>> from geoscript import feature
    >>> l = Layer() 
    >>> l.count()
    0
    >>> f = feature.Feature({'geom': geom.Point(1,2)})
    >>> l.add(f)
    >>> l.count()
    1
    
    *o* can also be specified as a ``dict`` or a ``list``:

    >>> from geoscript import geom
    >>> l = Layer()
    >>> l.add({'geom': geom.Point(1,2)})
    >>> l.add([geom.Point(1,2)])
    >>> l.count()
    2
    """
    if isinstance(o, feature.Feature):
      f = o
      if not f.schema:
        f.schema = self.schema
    elif isinstance(o, (dict,list)):
      f = self.schema.feature(o)
      
    fc = FeatureCollections.newCollection() 
    fc.add(f.f)
    self.fs.addFeatures(fc)

  def reproject(self, srs, name=None):
    tproj = proj.Projection(srs)
    natts = [(a.name, a.typ, tproj) if isinstance(a.typ,geom.Geometry) else (a.name,a.typ) for a in self.schema.attributes]
    nschema = feature.Schema(name if name else self.name, natts)    

    q = DefaultQuery(self.name, Filter.INCLUDE)
    q.coordinateSystemReproject = tproj._crs 

    fc = self.fs.getFeatures(q)
    i = fc.features()

    while i.hasNext():
      f = feature.Feature(schema=nschema, f=i.next())
      yield f
    
    fc.close(i)

  def toGML(self,out=sys.stdout):
    try:
      from net.opengis.wfs import WfsFactory
      from org.geotools.wfs.v1_1 import WFS, WFSConfiguration
      from org.geotools.xml import Encoder
    except ImportError:
      raise Exception('toGML() not available, GML libraries not on classpath.') 

    features = self.fs.features
    fc = WfsFactory.eINSTANCE.createFeatureCollectionType()
    fc.feature.add(features)

    e = Encoder(WFSConfiguration())        
    uri = self.fs.name.namespaceURI
    prefix = 'gt'
    e.namespaces.declarePrefix(prefix,uri)
    e.indenting = True
    e.encode(fc, WFS.FeatureCollection, out)

  def toJSON(self,out=sys.stdout):
    try:
      from org.geotools.geojson import GeoJSONWriter
    except ImportError:
      raise Exception('toJSON() not available, GeoJSON libraries not on classpath.')
    else:
      features = self.fs.features
      w = GeoJSONWriter() 
      w.write(features,out)

  def _filter(self, filter, default=Filter.INCLUDE):
     return CQL.toFilter(filter) if filter else default
