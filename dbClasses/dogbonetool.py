from ..common import dbUtils as
import adsk.core, adsk.fusion
from .dataclasses import DbParams 
from math import tan, pi

def getdbTool(edge: adsk.fusion.BRepEdge, parameters: DbParams, top_face_plane: adsk.fusion.Plane = None):  
    '''
    calculates and returns temp Brep tool body at this edge
    
    '''
    toolRadius = parameters.toolDia/2
    minPercent = 1+parameters.minimalPercent/100 if parameters.dbType == 'Minimal Dogbone' else  1
    
        
    (rslt, startPoint, endPoint) = edge.evaluator.getEndPoints()
    topPoint = endPoint
    
    if top_face_plane is not None:
        #need to ensure that the edge start and end points are the right way up
        cylinderAxisVector = startPoint.vectorTo(topPoint)
        infiniteLine = adsk.core.InfiniteLine3D.create(endPoint, cylinderAxisVector)
        topPoint = top_face_plane.intersectWithLine(infiniteLine)
        if startPoint.distanceTo(topPoint) < endPoint.distanceTo(topPoint):
            startPoint = endPoint
        endPoint = topPoint
    
    edgeVector = startPoint.vectorTo(endPoint)

    #   get the two faces associated with the edge
    
    face1 = edge.faces.item(0)
    face2 = edge.faces.item(1)
    
    face1Normal = face1.evaluator.getNormalAtPoint(face1.pointOnFace)[1]
    face2Normal = face2.evaluator.getNormalAtPoint(face2.pointOnFace)[1]
    
    #   find the vector the goes down the middle of the two faces - vector A + vector B
    if parameters.dbType == 'Mortise Dogbone':
        (edge1, edge2) = dbUtils.getCornerEdgesAtFace(parent.face, edge)
                    
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