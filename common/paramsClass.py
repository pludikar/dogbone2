# -*- coding: utf-8 -*-

from math import pi
import hashlib
import json 

#==============================================================================
# Would have used namedtuple, but it doesn't play nice with json - so have to do it longhand
#==============================================================================
class Params():
     dbParams = {}

     def __init__(self,
                    dataFrame=None,
                    activeFace=None,
                    activeRefEdge=None,
                    activeScribedEdge=None,
                    edgeType=None
                    ):
                    
          self.dbParams["data"] = dataFrame
          self.dbParams["face"] =  activeFace
          self.dbParams["refEdge"] =  activeRefEdge
          self.dbParams["scribedEdge"] =  activeScribedEdge
          self.dbParams["type"] = edgeType

     def __repr__(self):
          return self.jsonStr

     def __hash__(self):
          return self.hash

     def __eq__(self, other):
          return self.hash == other.hash

     @property
     def data(self):
          return self.dbParams["data"]

     @data.setter
     def data(self, dataFrame):
          self.dbParams["data"] =dataFrame

     @property
     def face(self):
          return self.dbParams["face"]

     @face.setter
     def fromTop(self, activeFace``):
          self.dbParams["face"] =activeFace

     @property
     def refEdge(self):
          return self.dbParams["refEdge"]
          
     @refEdge.setter
     def refEdge(self, activeRefEdge):
          self.dbParams["refEdge"] =activeRefEdge
          
     @property
     def scribedEdge(self):
          return self.dbParams["scribedEdge"]
          
     @scribedEdge.setter
     def scribedEdge(self,activeScribedEdge):
          self.dbParams["scribedEdge"] = activeScribedEdge
          
     @property
     def edgeType(self):
          return self.dbParams["type"]
          
     @edgeType.setter
     def edgeType(self, _edgeType):
          self.dbParams["type"] = _edgeType

     @property
     def jsonStr(self):
          return json.dumps(self.dbParams)

     @jsonStr.setter
     def jsonStr(self, jsonStr):
     #        TODO may need to do a consistency check on the imported resuls - just in case the json string is from an older version of the addin
          self.dbParams = json.loads(jsonStr)
          
     @property
     def isValid(self, paramToCheck):
     #     TODO  presently just does a key check, doesn't check value type - may or may not be neccessary in the futue
          for key in self.dbParams.keys():
               if key in paramToCheck:
                    continue
               return False
          return True

     @property
     def idTuple(self):
          return self._tuple