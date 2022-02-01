import logging
from tracemalloc import start
import adsk.core, adsk.fusion


from math import pi, tan

from typing import Type

from ..common import dbutils as dbUtils
from .dbEntity import DbEntity
from .dataclasses import DbParams

from math import sqrt, pi

logger = logging.getLogger('dogbone.dbEdge')

class DbEdge(DbEntity):

    def __init__(self, edge: adsk.fusion.BRepEdge, parent: Type):
        logger.info('---------------------------------creating edge---------------------------')
        super().__init__(edge)

        logger.debug('{} - edge initiated'.format(self.__hash__))
        self._topPlane = parent.topFacePlane
        self._parent = parent._hash
        # self.parameters = DbParams()

    @property
    def parent(self):
        return self._parent

    @property
    def parentObject(self):
        return self.register.getobject(self._parent)

    @property
    def topFacePlane(self):
        return self._topPlane

    def getdbTool(self, parameters: DbParams):  
        '''
        calculates and returns temp Brep tool body at this edge
        
        '''
        toolRadius = parameters.toolDia/2
        logger.debug(f'tool radius = {toolRadius}')

        minPercent = 1+parameters.minimalPercent/100 if parameters.dbType == 'Minimal Dogbone' else  1
        logger.debug(f'minPercent = {minPercent*100}')
        
        (rslt, startPoint, endPoint) = self.entity.evaluator.getEndPoints()
        topPoint = endPoint
        
        if parameters.fromTop:
            logger.debug('Calculating with topFacePlane')
            #need to ensure that the edge start and end points are the right way up
            cylinderAxisVector = startPoint.vectorTo(topPoint)
            infiniteLine = adsk.core.InfiniteLine3D.create(endPoint, cylinderAxisVector)
            topPoint = self.topFacePlane.intersectWithLine(infiniteLine)
            if startPoint.distanceTo(topPoint) < endPoint.distanceTo(topPoint):
                startPoint = endPoint
            endPoint = topPoint
        
        edgeVector = startPoint.vectorTo(endPoint)

        #   get the two faces associated with the edge
        
        face1, face2 = self.entity.faces
        
        face1Normal = face1.evaluator.getNormalAtPoint(face1.pointOnFace)[1]
        face2Normal = face2.evaluator.getNormalAtPoint(face2.pointOnFace)[1]
        
        #   find the vector the goes down the middle of the two faces - vector A + vector B
        if parameters.dbType == 'Mortise Dogbone':
            logger.debug('Doing Mortise Dogbone')
            (edge1, edge2) = dbUtils.getCornerEdgesAtFace(self.parentObject.entity, self.entity)
                        
            if parameters.longSide:
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
        cornerAngle = face1Normal.angleTo(face2Normal)
        logger.debug(f'cornerAngle = {cornerAngle*180/pi}deg')

        cornerTan = tan(cornerAngle)
        
        dbBox = None  #initialize temp brep box, incase it's going to be used - might not be needed
        #   TODO
        # if  cornerAngle != 0 and cornerAngle != pi/2:  # 0 means that the angle between faces is also 0 
        if  0 < cornerAngle < pi/2:  # 0 means that the angle between faces is also 0 

            # creating a box that will be used to clear the path the tool takes to the dogbone hole
            # box width is toolDia
            # box height is same as edge length
            # box length is from the hole centre to the point where the tool starts cutting the sides 

            #   find the orthogonal vector of the centreLine => make a copy then rotate by 90degrees
        
            orthogonalToCentreLine = centreLineVector.copy()

            rotationMatrix = adsk.core.Matrix3D.create()
            rotationMatrix.setToRotation(pi/2, edgeVector, startPoint)
            
            orthogonalToCentreLine.transformBy(rotationMatrix)
            centreLineVector.scaleBy(toolRadius*minPercent)
            orthogonalToCentreLine.scaleBy(toolRadius)
        
            boxLength = abs(toolRadius*cornerTan - toolRadius*minPercent)
            boxCentre = startPoint.copy()
            boxWidth = parameters.toolDia
            
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
