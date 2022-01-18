import logging
from pprint import pformat
import adsk.core, adsk.fusion

from sys import getrefcount as grc

from collections import defaultdict, namedtuple
from math import pi, tan

# import adsk.core, adsk.fusion
import traceback
import weakref
import json
from functools import reduce, lru_cache
from typing import Type

from ..common import dbutils as dbUtils
from . import dataclasses, register, dbFaces

from math import sqrt, pi

# class dbEdges():

#     def __init__(self, parentFace):
        
#     def __iter__(self):
#         for edge in self.edges:
#             yield edge

class dbEdge():

    def __init__(self, edge: adsk.fusion.BRepEdge, parentFace: Type):
        self.logger = logging.getLogger('dogbone.mgr.edge')
        self.logger.info('---------------------------------{}---------------------------'.format('creating edge'))
        register.EdgeObject(self)  #create an edge object 
        self.entity = edge  #brep edge
        self.edgeHash = hash(edge.entityToken)

        self._selected = True 
        # self.selected = True if attributes else False  #invokes selected property

        self.logger.debug('{} - edge initiated'.format(self.edgeHash))
        self.topPlane = parentFace.topFacePlane

    def __hash__(self):
        return self.edgeHash
        
    def __del__(self):
        self.logger.debug('edge {} deleted'.format(self.edgeHash))
        register.remove(self)
        self.logger.debug('{} - edge deleted'.format(self.edgeHash))

    @property
    def entity(self):
        return self.entity
            
    def updateAttributes(self):
        dbParamsJson = self._dbParams.jsonStr
        attr = self.edge.attributes.add(DBGROUP, 'edgeId:'+self.edgeHash, dbParamsJson)

    @property
    def dbParams(self):
        return self._dbParams
        
    @dbParams.setter
    def dbParams(self, dbParameters):
        self._dbParams = dbParameters
        self.updateAttributes()

    def getdbTool(self):  
        '''
        calculates and returns temp Brep tool body for the specific dogbone at this edge
        
        '''
        toolRadius = self.dbParameters.toolDia/2
        minPercent = 1+self.dbParameters.minimalPercent/100 if self.dbParameters.dbType == 'Minimal Dogbone' else  1
        
            
        (rslt, startPoint, endPoint) = self.dbParamsedge.evaluator.getEndPoints()
        topPoint = endPoint
        
        if self.dbParameters.topPlane:
            cylinderAxisVector = startPoint.vectorTo(self.topPoint)
            infiniteLine = adsk.core.InfiniteLine3D.create(endPoint, cylinderAxisVector)
            topPoint = self.face.topFacePlane.intersectWithLine(infiniteLine)
            if startPoint.distanceTo(topPoint) < endPoint.distanceTo(topPoint):
                startPoint = endPoint
            endPoint = topPoint
        
        edgeVector = startPoint.vectorTo(endPoint)
    
        #   get the two faces associated with the edge
        
        face1 = self.edge.faces.item(0)
        face2 = self.edge.faces.item(1)
        
        face1Normal = face1.evaluator.getNormalAtPoint(face1.pointOnFace)[1]
        face2Normal = face2.evaluator.getNormalAtPoint(face2.pointOnFace)[1]
        
        #   find the vector the goes down the middle of the two faces - vector A + vector B
        if self.dbParams.type == 'Mortise Dogbone':
            (edge1, edge2) = dbUtils.getCornerEdgesAtFace(self.parent.face, self.edge)
                        
            if self.longside:
                if (edge1.length > edge2.length):
                    centreLineVector = face1Normal
                else:
                    centreLineVector = face2Normal
            else:
                if (edge1.length > edge2.length):
                    centreLineVector = face2Normal
                else:
                    centreLineVector = face1Normal
        else:
            centreLineVector = face1Normal.copy()
            centreLineVector.add(face2Normal)
            centreLineVector.normalize()
        
        startPoint.translateBy(centreLineVector)
        endPoint.translateBy(centreLineVector)
       
        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
        dbBody = tempBrepMgr.createCylinderOrCone(startPoint, toolRadius, endPoint, toolRadius)
        cornerAngle = face1Normal.angleTo(face2Normal)/2
        cornerTan = tan(cornerAngle)
        
        dbBox = None  #initialize temp brep box, ncase it's going to be used - might not be needed
        #   TODO
        if cornerAngle != 0 and cornerAngle != pi/4:  # 0 means that the angle between faces is also 0 

            #   find the orthogonal vector of the centreLine = make a copy then rotate by 90degrees
        
            orthogonalToCentreLine = centreLineVector.copy()
    
            rotationMatrix = adsk.core.Matrix3D.create()
            rotationMatrix.setToRotation(pi/2, edgeVector, startPoint)
            
            orthogonalToCentreLine.transformBy(rotationMatrix)
            centreLineVector.scaleBy(toolRadius*minPercent)
            orthogonalToCentreLine.scaleBy(toolRadius)
        
            boxLength = abs(toolRadius*cornerTan - toolRadius*minPercent)
            boxCentre = startPoint.copy()
            boxWidth = self.dbParams.toolDia
            
            boxCentreVector = centreLineVector.copy()
            boxCentreVector.normalize()
            boxCentreVector.scaleBy(boxLength/2)
            
            boxCentreVertVect = edgeVector.copy()
            boxCentreVertVect.normalize()
            boxHeight = startPoint.distanceTo(endPoint)
            boxCentreVertVect.scaleBy(boxHeight/2)
            
            boxCentre.translateBy(boxCentreVector)
            boxCentre.translateBy(boxCentreVertVect)
    
            if (boxLength < 0.001):
                boxLength = .001 
            
            boundaryBox = adsk.core.OrientedBoundingBox3D.create(boxCentre, centreLineVector, orthogonalToCentreLine, boxLength, boxWidth, boxHeight)
            
            dbBox = tempBrepMgr.createBox(boundaryBox)
            tempBrepMgr.booleanOperation(dbBody, dbBox, adsk.fusion.BooleanTypes.UnionBooleanType)
            
        return dbBody  #temporary body ready to be unioned to other bodies

        
    @property
    def selected(self):
        return self._selected
        
    @selected.setter
    def selected(self, selected):
        self.logger.debug('{} - edge {}'.format(self.edgeHash, 'selected' if selected else 'deselected'))
        self.logger.debug('before selected edge count for face {} = {}'.format(self.parent.faceHash, len(self.selectedEdges)))
        if selected:
            self.selectedEdges[self.edgeHash] = self
            self.logger.debug('{} - edge appended to selectedEdges'.format(self.edgeHash))
        else: 
            del self.selectedEdges[self.edgeHash]
            self.logger.debug('{} - edge removed from selectedEdges'.format(self.edgeHash))
            self.edge.attributes.itemByName(DBGROUP, DBEDGE_SELECTED).deleteMe()
        self._selected = selected
        self.logger.debug('after selected edge count for face {} = {}'.format(self.parent.faceHash, len(self.selectedEdges)))
        
    def getAttributeValue(self):
        return self.face.attributes.itemByName(DBGROUP, 'edgeId:'+self.parent.faceHash).value

    def setAttributeValue(self, value):
        self.face.attributes.add(DBGROUP, 'edgeId:'+self.parent.faceHash, value)
        
    @property
    def topFacePlane(self):
        return self.group.topFacePlane
        
