import logging
import time
import adsk.core, adsk.fusion

from math import pi, tan
import os
import traceback
from functools import wraps
from pprint import pformat
from collections import defaultdict, namedtuple
from typing import Tuple, List
from functools import reduce, lru_cache
from .decorators import  tokeniseEntity

app = adsk.core.Application.get()  #might be better to put the next few lines into global!!
ui = app.userInterface
product = app.activeProduct
design: adsk.fusion.Design = product

getFaceNormal = lambda face: face.evaluator.getNormalAtPoint(face.pointOnFace)[1]
edgeVector = lambda coEdge:  coEdge.edge.evaluator.getEndPoints()[2].vectorTo(coEdge.edge.evaluator.getEndPoints()[1]) if coEdge.isOpposedToEdge else coEdge.edge.evaluator.getEndPoints()[1].vectorTo(coEdge.edge.evaluator.getEndPoints()[2]) 

logger = logging.getLogger('dogbone.utils')

@tokeniseEntity
@lru_cache(maxsize=120)
def get_component_hash(entityToken):
    '''
    returns the hash of an entity's Occurrence or its parent's body
    '''
    entity = design.findEntityByToken(entityToken)[0]  #TODO should probably check if there's more than 1 entity
    return hash(entity.assemblyContext.component.entityToken) if entity.assemblyContext else hash(entity.body.entityToken) 

def findInnerCorners(face):
    '''
    Finds candidate corners of a face suitable to create a dogbone on 
    '''
    logger.debug('find Inner Corners')
    face1: adsk.fusion.BRepFace = face
    if face1.objectType != adsk.fusion.BRepFace.classType():
        return False
    if face1.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
        return False
    faceNormal = getFaceNormal(face)
    edgeList = []
    for loop in face1.loops:
        for coEdge in loop.coEdges:
            vertex = coEdge.edge.endVertex if coEdge.isOpposedToEdge else coEdge.edge.startVertex

            edges = vertex.edges
            
            edgeCandidates = list(filter(lambda x: x != coEdge.previous.edge and x != coEdge.edge, edges))
            if not len(edgeCandidates):
                continue
#                    if edges.count != 3:
#                        break
            dbEdge = getDbEdge(edgeCandidates, faceNormal, vertex)
            if dbEdge:
                edgeList.append(dbEdge)
            
    return edgeList

def getDbEdge(edges, faceNormal, vertex, minAngle = 1/360*pi*2, maxAngle = 179/360*pi*2):
    """
    orders list of edges so all edgeVectors point out of startVertex
    returns: list of edgeVectors
    """
    
    for edge in edges:
        edgeVector = correctedEdgeVector(edge, vertex)
        if edgeVector.angleTo(faceNormal) == 0:
            continue
        cornerAngle = getAngleBetweenFaces(edge)
        return edge if cornerAngle < maxAngle and cornerAngle > minAngle else False
    return False


def getAngleBetweenFaces(edge: adsk.fusion.BRepEdge)-> float:
    '''
    With edge, return angle between the two faces that cojoin the edge
    '''
    # Verify that the two faces are planar.
    face1 = edge.faces.item(0)
    face2 = edge.faces.item(1)
    
    if not face1 or not face2:
        return False
    if face1.geometry.objectType != adsk.core.Plane.classType() or face2.geometry.objectType != adsk.core.Plane.classType():
        return False

    # Get the normal of each face.
    ret = face1.evaluator.getNormalAtPoint(face1.pointOnFace)
    normal1 = ret[1]
    ret = face2.evaluator.getNormalAtPoint(face2.pointOnFace)
    normal2 = ret[1]
    # Get the angle between the normals.
    normalAngle = normal1.angleTo(normal2)

    # Get the co-edge of the selected edge for face1.
    if edge.coEdges.item(0).loop.face == face1:
        coEdge = edge.coEdges.item(0)
    elif edge.coEdges.item(1).loop.face == face1:
        coEdge = edge.coEdges.item(1)

    # Create a vector that represents the direction of the co-edge.
    if coEdge.isOpposedToEdge:
        edgeDir = edge.startVertex.geometry.vectorTo(edge.endVertex.geometry)
    else:
        edgeDir = edge.endVertex.geometry.vectorTo(edge.startVertex.geometry)

    # Get the cross product of the face normals.
    cross = normal1.crossProduct(normal2)

    # Check to see if the cross product is in the same or opposite direction
    # of the co-edge direction.  If it's opposed then it's a convex angle.
    if edgeDir.angleTo(cross) > pi/2:
        angle = (pi * 2) - (pi - normalAngle)
    else:
        angle = pi - normalAngle

    return angle

def findExtent(face: adsk.fusion.BRepFace, edge: adsk.fusion.BRepEdge):
    
    if edge.startVertex in face.vertices:
        endVertex = edge.endVertex
    else:
        endVertex = edge.startVertex
    return endVertex

    
def correctedEdgeVector(edge:adsk.fusion.BRepEdge, refVertex: adsk.fusion.BRepVertex):
    if edge.startVertex.geometry.isEqualTo(refVertex.geometry):
        return edge.startVertex.geometry.vectorTo(edge.endVertex.geometry)
    else:
        return edge.endVertex.geometry.vectorTo(edge.startVertex.geometry)
    return False

def correctedSketchEdgeVector(edge, refPoint):
    if edge.startSketchPoint.geometry.isEqualTo(refPoint.geometry):
        return edge.startSketchPoint.geometry.vectorTo(edge.endSketchPoint.geometry)
    else:
        return edge.endSketchPoint.geometry.vectorTo(edge.startSketchPoint.geometry)
    return False
    

def isEdgeAssociatedWithFace(face:adsk.fusion.BRepFace, edge:adsk.fusion.BRepEdge):
    
    # have to check both ends - not sure which way around the start and end vertices are
    if edge.startVertex in face.vertices:
        return True
    if edge.endVertex in face.vertices:
        return True
    return False
    
def getCornerEdgesAtFace(face:adsk.fusion.BRepFace, edge:adsk.fusion.BRepEdge)->Tuple[adsk.fusion.BRepEdge, adsk.fusion.BRepEdge]:
    '''
    With orthogonal corner edge to face, returns the two edges on the Face that meet at the corner
    '''
    #not sure which end is which - so test edge ends for inclusion in face
    if edge.startVertex in face.vertices:
        startVertex = edge.startVertex
    else:
        startVertex = edge.endVertex 
    #edge has 2 adjacent faces - therefore the face that isn't from the 3 faces of startVertex, has to be the top face edges
#    returnVal = [edge1 for edge1 in edge.startVertex.edges if edge1 in face.edges]
    logger = logging.getLogger(__name__)
    returnVal = []
    for edge1 in startVertex.edges:
        if edge1 not in face.edges:
            continue
        logger.debug('edge {} added to adjacent edge list'.format(edge1.tempId))
        returnVal.append(edge1)
    if len(returnVal)!= 2:
        raise NameError('returnVal len != 2')
        
    return (returnVal[0], returnVal[1])
    
def getVertexAtFace(face:adsk.fusion.BRepFace, edge:adsk.fusion.BRepEdge):
    '''
    With orthogonal corner edge to face, returns the corner vertex on the Face
    
    '''
    if edge.startVertex in face.vertices:
        return edge.startVertex
    else:
        return edge.endVertex
    return False
    
def messageBox(*args):
    adsk.core.Application.get().userInterface.messageBox(*args)


def getTopFacePlane(faceEntity: adsk.fusion.BRepFace)->Tuple[adsk.core.Plane, int]:
    '''
    Creates a plane at the highest point of a body - relative to the normal of a face
    This allows dogbones to be extruded from any point on the body, without being associated with an adjacent face 
    returns created plane and hash of topFace that it is created from
    '''
    normal = getFaceNormal(faceEntity)
    refPlane = adsk.core.Plane.create(faceEntity.vertices.item(0).geometry, normal)
    refLine = adsk.core.InfiniteLine3D.create(faceEntity.vertices.item(0).geometry, normal)
    refPoint = refPlane.intersectWithLine(refLine)
    faceList = []
    body: adsk.fusion.BRepBody = faceEntity.body
    def calcDistance(face):
        facePlane = adsk.core.Plane.create(face.vertices.item(0).geometry, normal)
        intersectionPoint = facePlane.intersectWithLine(refLine)
        directionVector = refPoint.vectorTo(intersectionPoint)
        return directionVector.dotProduct(normal)
    for face in body.faces:
        if not normal.isParallelTo(getFaceNormal(face)):
            continue
        facePlane = adsk.core.Plane.create(face.vertices.item(0).geometry, normal)
        intersectionPoint = facePlane.intersectWithLine(refLine)
        directionVector = refPoint.vectorTo(intersectionPoint)
        distance = directionVector.dotProduct(normal)
        faceList.append([face, distance])
    sortedFaceList = sorted(faceList, key = lambda x: x[1])
    top = sortedFaceList[-1][0]
    return (adsk.core.Plane.create(top.pointOnFace, getFaceNormal(top)),hash(top.entityToken))

def getAllParallelFaces(faceEntity: adsk.fusion.BRepFace)->List[adsk.fusion.BRepFace]:
    '''
    gets All faces that are parallel and facing same way
    '''
    normal = getFaceNormal(faceEntity)
    body: adsk.fusion.BRepBody = faceEntity.body

    faceList = list(filter(lambda face: normal.isEqualTo(getFaceNormal(face)), body.faces))
    return faceList

 

def getTranslateVectorBetweenFaces(fromFace: adsk.fusion.BRepFace, toFace: adsk.fusion.BRepFace)->adsk.core.Vector3D:
    """
    returns Vector needed to translate one face to another
    """
    logger = logging.getLogger(__name__)

    normal = getFaceNormal(fromFace)
    if not normal.isParallelTo(getFaceNormal(fromFace)):
        return False

    fromFacePlane = adsk.core.Plane.create(fromFace.vertices.item(0).geometry, normal)
    fromFaceLine = adsk.core.InfiniteLine3D.create(fromFace.vertices.item(0).geometry, normal)
    fromFacePoint = fromFacePlane.intersectWithLine(fromFaceLine)
    
    toFacePlane = adsk.core.Plane.create(toFace.vertices.item(0).geometry, normal)
    toFacePoint = toFacePlane.intersectWithLine(fromFaceLine)
    translateVector = fromFacePoint.vectorTo(toFacePoint)
    return translateVector