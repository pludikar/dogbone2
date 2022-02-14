from calendar import c
import logging
from tracemalloc import start
import adsk.core, adsk.fusion


from math import pi, tan

from typing import Type

from ..common import dbutils as dbUtils
from .dbEntity import DbEntity
from .dataclasses import DbParams
from ..common import common as g

from math import sqrt, pi

logger = logging.getLogger('dogbone.dbEdge')

class DbEdge(DbEntity):

    def __init__(self, edge: adsk.fusion.BRepEdge, parent: Type):
        logger.info('---------------------------------creating edge---------------------------')
        super().__init__(edge)

        self._topPlane = parent.topFacePlane
        self._parent = parent.entityToken
        self._type = 'edge'
        logger.debug(f'edge initiated - {self}')
        # self.params = DbParams()

    @property
    def parent(self):
        return self._parent

    @property
    def parentObject(self):
        return self.register.getobject(self._parent)

    @property
    def topFacePlane(self):
        return self._topPlane

    def getdbTool(self, params: DbParams):
        '''
        calculates and returns temp Brep tool body for this edge
        
        '''
        logger.debug(f'processing {self}-----------------------------')
        
        #   get the two faces associated with the edge
        
        face1, face2 = self.entity.faces
        
        face1Normal = face1.evaluator.getNormalAtPoint(face1.pointOnFace)[1]
        face2Normal = face2.evaluator.getNormalAtPoint(face2.pointOnFace)[1]

        cornerAngle = pi - face1Normal.angleTo(face2Normal)
        
        logger.debug(f'cornerAngle = {cornerAngle*180/pi}deg')

        if cornerAngle < params.minAngleLimit:
            return False

        toolRadius = params.toolDia/2
        logger.debug(f'tool radius = {toolRadius}')

        minPercent = 1+params.minimalPercent/100 if params.dbType == 'Minimal Dogbone' else  1
        logger.debug(f'minPercent = {minPercent*100}')
        
        (_, startPoint, endPoint) = self.entity.evaluator.getEndPoints()
        topPoint = endPoint
        
        if params.fromTop:
            logger.debug('Calculating with topFacePlane')
            #need to ensure that the edge start and end points are the right way up
            cylinderAxisVector = startPoint.vectorTo(topPoint)
            infiniteLine = adsk.core.InfiniteLine3D.create(endPoint, cylinderAxisVector)
            topPoint = self.topFacePlane.intersectWithLine(infiniteLine)
            if startPoint.distanceTo(topPoint) < endPoint.distanceTo(topPoint):
                startPoint = endPoint
            endPoint = topPoint
        
        edgeVector = startPoint.vectorTo(endPoint)

        
        #   find the vector the goes down the middle of the two faces - vector A + vector B
        if params.dbType == 'Mortise Dogbone':
            logger.debug('Doing Mortise Dogbone')
            (edge1, edge2) = dbUtils.getCornerEdgesAtFace(self.parentObject.entity, self.entity)
                        
            if params.longSide:
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
            logger.debug('Doing Normal Dogbone')
            centreLineVector = face1Normal.copy()
            #get vector midway between faces - adding the two edge vectors will do that!
            centreLineVector.add(face2Normal)
            centreLineVector.normalize()
            centreLineVector.scaleBy(toolRadius)

        logger.debug(f'startpoint vector x={startPoint.x} y={startPoint.y} z={startPoint.z}')
        
        startPoint.translateBy(centreLineVector)
        endPoint.translateBy(centreLineVector)
        logger.debug(f'after translation  - startpoint vector x={startPoint.x} y={startPoint.y} z={startPoint.z}')
        
        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
        dbBody = tempBrepMgr.createCylinderOrCone(startPoint, toolRadius, endPoint, toolRadius)

        
        dbBox = None  #initialize temp brep box, incase it's going to be used - might not be needed
        #   TODO
        # if  cornerAngle != 0 and cornerAngle != pi/2:  # 0 means that the angle between faces is also 0 
        if  params.minAngleLimit < cornerAngle < params.maxAngleLimit:  # 0 means that the angle between faces is also 0 

            # creating a box that will be used to clear the path the tool takes to the dogbone hole
            # box width is toolDia
            # box height is same as edge length
            # box length is from the hole centre to the point where the tool starts cutting the sides


            #   find the orthogonal vector of the centreLine => make a copy then rotate by 90degrees
            logger.debug("Adding acute angle clearance box")
            cornerTan = tan(cornerAngle/2)

            rotationMatrix = adsk.core.Matrix3D.create()
            rotationMatrix.setToRotation(pi/2, edgeVector, startPoint)
            
            widthVectorDirection = centreLineVector.copy()
            widthVectorDirection.transformBy(rotationMatrix)
        
            boxLength = toolRadius*minPercent/cornerTan - toolRadius
            boxCentre = startPoint.copy()
            boxWidth = params.toolDia
            
            boxCentreVector = centreLineVector.copy()
            boxCentreVector.normalize()
            boxCentreVector.scaleBy(boxLength/2)
            
            boxCentreHeightVect = edgeVector.copy()
            boxCentreHeightVect.normalize()
            boxHeight = startPoint.distanceTo(topPoint)
            #need to move Box centre point by height /2 to keep top and bottom aligned with cylinder 
            boxCentreHeightVect.scaleBy(boxHeight/2) 
            
            boxCentre.translateBy(boxCentreVector)
            boxCentre.translateBy(boxCentreHeightVect)

            if (boxLength < 0.001):
                boxLength = .001 
            
            boundaryBox = adsk.core.OrientedBoundingBox3D.create(centerPoint = boxCentre, 
                                                                lengthDirection = centreLineVector, 
                                                                widthDirection = widthVectorDirection, 
                                                                length = boxLength, 
                                                                width = boxWidth, 
                                                                height = boxHeight)
            
            dbBox = tempBrepMgr.createBox(boundaryBox)
            tempBrepMgr.booleanOperation(targetBody = dbBody, 
                                        toolBody = dbBox, 
                                        booleanType = adsk.fusion.BooleanTypes.UnionBooleanType)
            
        return dbBody  #temporary body ready to be unioned to other bodies    
