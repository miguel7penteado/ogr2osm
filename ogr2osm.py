#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" ogr2osm beta

This program takes any vector data understadable by OGR and outputs an OSM file
with that data.

By default tags will be naively copied from the input data. Hooks are provided
so that, with a little python programming, you can translate the tags however
you like. More hooks are provided so you can filter or even modify the global_feicoes
themselves.

To use the hooks, create a file in the translations/ directory called myfile.py
and run ogr2osm.py -t myfile. This file should define a function with the name
of each hook you want to use. For an example, see the uvmtrans.py file.

The program will use projection metadata from the source, if it has any. If
there is no projection information, or if you want to override it, you can use
-e or -p to specify an EPSG code or Proj.4 string, respectively. If there is no
projection metadata and you do not specify one, EPSG:4326 will be used (WGS84
latitude-longitude)

For additional usage information, run ogr2osm.py --help



Copyright (c) 2012 The University of Vermont
<andrew.guertin@uvm.edu
Released under the MIT license: http://opensource.org/licenses/mit-license.php

Based very heavily on code released under the following terms:

(c) Iván Sánchez Ortega, 2009
<ivan@sanchezortega.es>
###############################################################################
#  "THE BEER-WARE LICENSE":                                                   #
#  <ivan@sanchezortega.es> wrote this file. As long as you retain this notice #
#  you can do whatever you want with this stuff. If we meet some day, and you #
#  think this stuff is worth it, you can buy me a beer in return.             #
###############################################################################

"""


import sys
import os
from optparse import OptionParser
import logging as l
l.basicConfig(level=l.DEBUG, format="%(message)s")

from osgeo import ogr
from osgeo import osr

from SimpleXMLWriter import XMLWriter

# Setup program usage
usage = "usage: %prog SRCFILE"
interpretador = OptionParser(usage=usage)

interpretador.add_option("-t", "--translation", dest="translationMethod", metavar="TRANSLATION", help="Select the attribute-tags translation method. See " +  "the translations/ directory for valid values.")

interpretador.add_option("-o", "--output", dest="outputFile", metavar="OUTPUT", help="Set destination .osm file name and location.")

interpretador.add_option("-e", "--epsg", dest="sourceEPSG", metavar="EPSG_CODE", help="EPSG code of source file. Do not include the " + "'EPSG:' prefix. If specified, overrides projection " + "from source metadata if it exists.")

interpretador.add_option("-p", "--proj4", dest="sourcePROJ4", metavar="PROJ4_STRING", help="PROJ.4 string. If specified, overrides projection " + "from source metadata if it exists.")

interpretador.add_option("-v", "--verbose", dest="verbose", action="store_true")

interpretador.add_option("-d", "--debug-tags", dest="debugTags", action="store_true", help="Output the tags for every feature parsed.")
interpretador.add_option("-f", "--force", dest="forceOverwrite", action="store_true", help="Force overwrite of output file.")

interpretador.set_defaults(sourceEPSG=None, sourcePROJ4=None, verbose=False, debugTags=False, translationMethod=None, outputFile=None, forceOverwrite=False)

# Interpretar e processar argumentos
(options, argumentos) = interpretador.parse_args()

try:
    if options.sourceEPSG:
        options.sourceEPSG = int(options.sourceEPSG)
except:
    interpretador.error("EPSG code must be numeric (e.g. '4326', not 'epsg:4326')")

if len(argumentos) < 1:
    interpretador.print_help()
    interpretador.error("you must specify a source filename")
elif len(argumentos) > 1:
    interpretador.error("you have specified too many arguments, " + "only supply the source filename")

# Arquivo de entrada e saida
# Se nenhum arquivo de saida eh fornecido, use o nome base do arquivo de entrada fornecido com extensao .osm
arquivo_entrada = os.path.realpath(argumentos[0])

if options.outputFile is not None:
    options.outputFile = os.path.realpath(options.outputFile)
else:
    (base, ext) = os.path.splitext(os.path.basename(arquivo_entrada))
    options.outputFile = os.path.join(os.getcwd(), base + ".osm")
if not options.forceOverwrite and os.path.exists(options.outputFile):
    interpretador.error("ERROR: output file '%s' exists" % (options.outputFile))
l.info("Preparing to convert file '%s' to '%s'." % (arquivo_entrada, options.outputFile))

# Projecao
if not options.sourcePROJ4 and not options.sourceEPSG:
    l.info("Will try to detect projection from source metadata, or fall back to EPSG:4326")
elif options.sourcePROJ4:
    l.info("Will use the PROJ.4 string: " + options.sourcePROJ4)
elif options.sourceEPSG:
    l.info("Will use EPSG:" + str(options.sourceEPSG))


# Precisa de conteudo para localizar metodos de traducao
if options.translationMethod:
    # adiciona diretorios ao caminho se necessario
    (root, ext) = os.path.splitext(options.translationMethod)
    if os.path.exists(options.translationMethod) and ext == '.py':
        # usuario forneceu arquivos de traducao diretamente
        sys.path.insert(0, os.path.dirname(root))
    else:
        # first check translations in the subdir translations of cwd
        sys.path.insert(0, os.path.join(os.getcwd(), "translations"))
        # then check subdir of script dir
        sys.path.insert(1, os.path.join(os.path.abspath(__file__), "translations"))
        # (the cwd will also be checked implicityly)

    # strip .py if present, as import wants just the module name
    if ext == '.py':
        options.translationMethod = os.path.basename(root)

    try:
        translations = __import__(options.translationMethod)
    except:
        interpretador.error("Nao consegui carregar o metodo de traducao '%s'. O script de traducao "
               "deve estar em seu diretorio atual, ou no subdiretorio"
               "translations/ do seu diretorio atual ou do diretorio ogr2osm.py "
               ".") % (options.translationMethod)
    l.info("Metodo de traducao '%s' carregado com sucesso ('%s')."
           % (options.translationMethod, os.path.realpath(translations.__file__)))
else:
    import types
    translations = types.ModuleType("translationmodule")
    l.info("Using default translations")

try:
    translations.filterLayer(None)
    l.debug("Using user filterLayer")
except:
    l.debug("Using default filterLayer")
    translations.filterLayer = lambda layer: layer

try:
    translations.filterFeature(None, None, None)
    l.debug("Using user filterFeature")
except:
    l.debug("Using default filterFeature")
    translations.filterFeature = lambda feature, fieldNames, reproject: feature

try:
    translations.filterTags(None)
    l.debug("Using user filterTags")
except:
    l.debug("Using default filterTags")
    translations.filterTags = lambda tags: tags

try:
    translations.filterFeaturePost(None, None, None)
    l.debug("Using user filterFeaturePost")
except:
    l.debug("Using default filterFeaturePost")
    translations.filterFeaturePost = lambda feature, fieldNames, reproject: feature

try:
    translations.preOutputTransform(None, None)
    l.debug("Using user preOutputTransform")
except:
    l.debug("Usando preOutputTransform padrao")
    translations.preOutputTransform = lambda global_geometrias, global_feicoes: None

# Checadas as corretas quantidades de parametros, vamos ao programa 

# Algumas variaveis globais para guardar dados...
global_geometrias = []
global_feicoes = []

# Funcao Helper para obter novo ID
contador_Id_Elementos = 0
def getNewID():
    global contador_Id_Elementos
    contador_Id_Elementos -= 1
    return contador_Id_Elementos

# Classes
class Geometry(object):
    id = 0
    def __init__(self):
        self.id = getNewID()
        self.parents = set()
        global global_geometrias
        global_geometrias.append(self)

    def replacejwithi(self, i, j):
        pass

    def addparent(self, parent):
        self.parents.add(parent)

    def removeparent(self, parent, shoulddestroy=True):
        self.parents.discard(parent)
        if shoulddestroy and len(self.parents) == 0:
            global global_geometrias
            global_geometrias.remove(self)

class Point(Geometry):
    def __init__(self, x, y):
        Geometry.__init__(self)
        self.x = x
        self.y = y
    def replacejwithi(self, i, j):
        pass

class Way(Geometry):
    def __init__(self):
        Geometry.__init__(self)
        self.points = []
    def replacejwithi(self, i, j):
        self.points = map(lambda x: i if x == j else x, self.points)
        j.removeparent(self)
        i.addparent(self)

class Relation(Geometry):
    def __init__(self):
        Geometry.__init__(self)
        self.members = []
    def replacejwithi(self, i, j):
        self.members = map(lambda x: i if x == j else x, self.members)
        j.removeparent(self)
        i.addparent(self)

class Feature(object):
    geometry = None
    tags = {}
    def __init__(self):
        global global_feicoes
        global_feicoes.append(self)
    def replacejwithi(self, i, j):
        if self.geometry == j:
            self.geometry = i
        j.removeparent(self)
        i.addparent(self)

def getFileData(filename):
    if not os.path.isfile(filename):
        interpretador.error("the file '%s' does not exist" % (filename))
    dataSource = ogr.Open(filename, 0)  # 0 means read-only
    if dataSource is None:
        l.error('OGR failed to open ' + filename + ', format may be unsuported')
        sys.exit(1)
    return dataSource

def parseData(dataSource):
    l.debug("Parsing data")
    global translations
    for i in range(dataSource.GetLayerCount()):
        layer = dataSource.GetLayer(i)
        layer.ResetReading()
        parseLayer(translations.filterLayer(layer))

def getTransform(layer):
    global options
    # First check if the user supplied a projection, then check the layer,
    # then fall back to a default
    spatialRef = None
    if options.sourcePROJ4:
        spatialRef = osr.SpatialReference()
        spatialRef.ImportFromProj4(options.sourcePROJ4)
    elif options.sourceEPSG:
        spatialRef = osr.SpatialReference()
        spatialRef.ImportFromEPSG(options.sourceEPSG)
    else:
        spatialRef = layer.GetSpatialRef()
        if spatialRef != None:
            l.info("Detected projection metadata:\n" + str(spatialRef))
        else:
            l.info("No projection metadata, falling back to EPSG:4326")

    if spatialRef == None:
        # No source proj specified yet? Then default to do no reprojection.
        # Some python magic: skip reprojection altogether by using a dummy
        # lamdba funcion. Otherwise, the lambda will be a call to the OGR
        # reprojection stuff.
        reproject = lambda(geometry): None
    else:
        destSpatialRef = osr.SpatialReference()
        # Destionation projection will *always* be EPSG:4326, WGS84 lat-lon
        destSpatialRef.ImportFromEPSG(4326)
        coordTrans = osr.CoordinateTransformation(spatialRef, destSpatialRef)
        reproject = lambda(geometry): geometry.Transform(coordTrans)

    return reproject

def getLayerFields(layer):
    featureDefinition = layer.GetLayerDefn()
    fieldNames = []
    fieldCount = featureDefinition.GetFieldCount()
    for j in range(fieldCount):
        fieldNames.append(featureDefinition.GetFieldDefn(j).GetNameRef())
    return fieldNames

def getFeatureTags(ogrfeature, fieldNames):
    tags = {}
    for i in range(len(fieldNames)):
        tags[fieldNames[i]] = ogrfeature.GetFieldAsString(i)
    return translations.filterTags(tags)

def parseLayer(layer):
    if layer is None:
        return
    fieldNames = getLayerFields(layer)
    reproject = getTransform(layer)
    
    for j in range(layer.GetFeatureCount()):
        ogrfeature = layer.GetNextFeature()
        parseFeature(translations.filterFeature(ogrfeature, fieldNames, reproject), fieldNames, reproject)

def parseFeature(ogrfeature, fieldNames, reproject):
    if ogrfeature is None:
        return

    ogrgeometry = ogrfeature.GetGeometryRef()
    if ogrgeometry is None:
        return
    reproject(ogrgeometry)
    geometry = parseGeometry(ogrgeometry)
    if geometry is None:
        return

    feature = Feature()
    feature.tags = getFeatureTags(ogrfeature, fieldNames)
    feature.geometry = geometry
    geometry.addparent(feature)

    translations.filterFeaturePost(feature, ogrfeature, ogrgeometry)
    

def parseGeometry(ogrgeometry):
    geometryType = ogrgeometry.GetGeometryType()

    if (geometryType == ogr.wkbPoint or
        geometryType == ogr.wkbPoint25D):
        return parsePoint(ogrgeometry)
    elif (geometryType == ogr.wkbLineString or
          geometryType == ogr.wkbLinearRing or
          geometryType == ogr.wkbLineString25D):
#         geometryType == ogr.wkbLinearRing25D does not exist
        return parseLineString(ogrgeometry)
    elif (geometryType == ogr.wkbPolygon or
          geometryType == ogr.wkbPolygon25D):
        return parsePolygon(ogrgeometry)
    elif (geometryType == ogr.wkbMultiPoint or
          geometryType == ogr.wkbMultiLineString or
          geometryType == ogr.wkbMultiPolygon or
          geometryType == ogr.wkbGeometryCollection or
          geometryType == ogr.wkbMultiPoint25D or
          geometryType == ogr.wkbMultiLineString25D or
          geometryType == ogr.wkbMultiPolygon25D or
          geometryType == ogr.wkbGeometryCollection25D):
        return parseCollection(ogrgeometry)
    else:
        l.warning("unhandled geometry, type: " + str(geometryType))
        return None

def parsePoint(ogrgeometry):
    x = ogrgeometry.GetX()
    y = ogrgeometry.GetY()
    geometry = Point(x, y)
    return geometry

def parseLineString(ogrgeometry):
    geometry = Way()
    # LineString.GetPoint() returns a tuple, so we can't call parsePoint on it
    # and instead have to create the point ourself
    for i in range(ogrgeometry.GetPointCount()):
        (x, y, unused) = ogrgeometry.GetPoint(i)
        mypoint = Point(x, y)
        geometry.points.append(mypoint)
        mypoint.addparent(geometry)
    return geometry

def parsePolygon(ogrgeometry):
    # Special case polygons with only one ring. This does not (or at least
    # should not) change behavior when simplify relations is turned on.
    if ogrgeometry.GetGeometryCount() == 0:
        l.warning("Polygon with no rings?")
    elif ogrgeometry.GetGeometryCount() == 1:
        return parseLineString(ogrgeometry.GetGeometryRef(0))
    else:
        geometry = Relation()
        try:
            exterior = parseLineString(ogrgeometry.GetGeometryRef(0))
            exterior.addparent(geometry)
        except:
            l.warning("Polygon with no exterior ring?")
            return None
        geometry.members.append((exterior, "outer"))
        for i in range(1, ogrgeometry.GetGeometryCount()):
            interior = parseLineString(ogrgeometry.GetGeometryRef(i))
            interior.addparent(geometry)
            geometry.members.append((interior, "inner"))
        return geometry

def parseCollection(ogrgeometry):
    # OGR MultiPolygon maps easily to osm multipolygon, so special case it
    # TODO: Does anything else need special casing?
    geometryType = ogrgeometry.GetGeometryType()
    if (geometryType == ogr.wkbMultiPolygon or
        geometryType == ogr.wkbMultiPolygon25D):
        geometry = Relation()
        for polygon in range(ogrgeometry.GetGeometryCount()):
            exterior = parseLineString(ogrgeometry.GetGeometryRef(polygon).GetGeometryRef(0))
            exterior.addparent(geometry)
            geometry.members.append((exterior, "outer"))
            for i in range(1, ogrgeometry.GetGeometryRef(polygon).GetGeometryCount()):
                interior = parseLineString(ogrgeometry.GetGeometryRef(polygon).GetGeometryRef(i))
                interior.addparent(geometry)
                geometry.members.append((interior, "inner"))
    else:
        geometry = Relation()
        for i in range(ogrgeometry.GetGeometryCount()):
            member = parseGeometry(ogrgeometry.GetGeometryRef(i))
            member.addparent(geometry)
            geometry.members.append((member, "member"))
        return geometry

def mergePoints():
    l.debug("Merging points")
    global global_geometrias
    points = [geometry for geometry in global_geometrias if type(geometry) == Point]
    
    # Make list of Points at each location
    l.debug("Making list")
    pointcoords = {}
    for i in points:
        try:
            pointcoords[(i.x, i.y)].append(i)
        except KeyError:
            pointcoords[(i.x, i.y)] = [i]

    # Use list to get rid of extras
    l.debug("Checking list")
    for (location, pointsatloc) in pointcoords.items():
        if len(pointsatloc) > 1:
            for point in pointsatloc[1:]:
                for parent in set(point.parents):
                    parent.replacejwithi(pointsatloc[0], point)
        
def output():
    l.debug("Outputting XML")
    # First, set up a few data structures for optimization purposes
    global global_geometrias, global_feicoes
    nodes = [geometry for geometry in global_geometrias if type(geometry) == Point]
    ways = [geometry for geometry in global_geometrias if type(geometry) == Way]
    relations = [geometry for geometry in global_geometrias if type(geometry) == Relation]
    featuresmap = {feature.geometry : feature for feature in global_feicoes}

    w = XMLWriter(open(options.outputFile, 'w'))
    w.start("osm", version='0.6', generator='uvmogr2osm')

    for node in nodes:
        w.start("node", visible="true", id=str(node.id), lat=str(node.y), lon=str(node.x))
        if node in featuresmap:
            for (key, value) in featuresmap[node].tags.items():
                w.element("tag", k=key, v=value)
        w.end("node")

    for way in ways:
        w.start("way", visible="true", id=str(way.id))
        for node in way.points:
            w.element("nd", ref=str(node.id))
        if way in featuresmap:
            for (key, value) in featuresmap[way].tags.items():
                w.element("tag", k=key, v=value)
        w.end("way")

    for relation in relations:
        w.start("relation", visible="true", id=str(relation.id))
        for (member, role) in relation.members:
            w.element("member", type="way", ref=str(member.id), role=role)
        if relation in featuresmap:
            for (key, value) in featuresmap[relation].tags.items():
                w.element("tag", k=key, v=value)
        w.end("relation")

    w.end("osm")


# Fluxo Principal
meus_dados = getFileData(arquivo_entrada)
parseData(meus_dados)
mergePoints()
translations.preOutputTransform(global_geometrias, global_feicoes)
output()
