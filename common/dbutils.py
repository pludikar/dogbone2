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
from . import common as g


getFaceNormal = lambda face: face.evaluator.getNormalAtPoint(face.pointOnFace)[1]
edgeVector = lambda coEdge:  coEdge.edge.evaluator.getEndPoints()[2].vectorTo(coEdge.edge.evaluator.getEndPoints()[1]) if coEdge.isOpposedToEdge else coEdge.edge.evaluator.getEndPoints()[1].vectorTo(coEdge.edge.evaluator.getEndPoints()[2]) 

logger = logging.getLogger('dogbone.utils')

@tokeniseEntity
# @lru_cache(maxsize=120)
def get_component_token(entityToken):
    '''
    returns the hash of an entity's Occurrence or its parent's body
    '''
    entity = g._design.findEntityByToken(entityToken)[0]  #TODO should probably check if there's more than 1 entity
    return entity.assemblyContext.component.entityToken if entity.assemblyContext else entity.body.entityToken 

def findInnerCorners(face: adsk.fusion.BRepFace, minAngle = 5 /180 * pi, maxAngle = 100/ 180 * pi):
    '''
    Finds candidate corners of a face suitable to create a dogbone on 
    '''
    
    if face.objectType != adsk.fusion.BRepFace.classType():
        return False
    if face.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
        return False
    faceNormal = getFaceNormal(face)
    edgeList = []
    for loop in face.loops:
        logger.debug(f'Loop count = {loop.coEdges.count}')
        for coEdge in loop.coEdges:
            vertex = coEdge.edge.endVertex if coEdge.isOpposedToEdge else coEdge.edge.startVertex

            edges = vertex.edges
            
            edgeCandidates = list(filter(lambda x: x != coEdge.previous.edge and x != coEdge.edge, edges))
            if not len(edgeCandidates):
                continue
            dbEdge = getDbEdge(edges = edgeCandidates, 
                                faceNormal = faceNormal, 
                                vertex = vertex,
                                minAngle = minAngle,
                                maxAngle = maxAngle)
            if dbEdge:
                edgeList.append(dbEdge)

    return edgeList

def getDbEdge(edges, faceNormal, vertex, minAngle = 1/180*pi, maxAngle = 179/180*pi):
    """
    orders list of edges so all edgeVectors point out of startVertex
    returns: list of edgeVectors
    """
    
    for edge in edges:
        edgeVector = correctedEdgeVector(edge, vertex)
        if edgeVector.angleTo(faceNormal) == 0:
            continue
        cornerAngle = getAngleBetweenFaces(edge)
        return edge if minAngle < cornerAngle < maxAngle else False
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
    if (face1.geometry.objectType != adsk.core.Plane.classType()
        or face2.geometry.objectType != adsk.core.Plane.classType()):
        return False

    # Get the normal of each face.
    (_, normal1) = face1.evaluator.getNormalAtPoint(face1.pointOnFace)
    (_, normal2) = face2.evaluator.getNormalAtPoint(face2.pointOnFace)

    # Get the angle between the normals.
    normalAngle = normal1.angleTo(normal2)

    # Get the co-edge of the selected edge for face1.
    if edge.coEdges.item(0).loop.face == face1:
        coEdge = edge.coEdges.item(0)
    elif edge.coEdges.item(1).loop.face == face1:
        coEdge = edge.coEdges.item(1)

    # Create a vector that represents the direction of the co-edge.
    edgeDir = edge.startVertex.geometry.vectorTo(edge.endVertex.geometry) if coEdge.isOpposedToEdge else edge.endVertex.geometry.vectorTo(edge.startVertex.geometry)

    # Get the cross product of the face normals.
    cross = normal1.crossProduct(normal2)

    # Check to see if the cross product is in the same or opposite direction
    # of the co-edge direction.  If it's opposed then it's a convex angle.
    return  (pi * 2) - (pi - normalAngle) if edgeDir.angleTo(cross) > pi/2 else pi - normalAngle

def findExtent(face: adsk.fusion.BRepFace, edge: adsk.fusion.BRepEdge):
    
    return  edge.endVertex if edge.startVertex in face.vertices else edge.startVertex

    
def correctedEdgeVector(edge:adsk.fusion.BRepEdge, refVertex: adsk.fusion.BRepVertex):
    if edge.startVertex.geometry.isEqualTo(refVertex.geometry):
        return edge.startVertex.geometry.vectorTo(edge.endVertex.geometry)
    return edge.endVertex.geometry.vectorTo(edge.startVertex.geometry)

def correctedSketchEdgeVector(edge, refPoint):
    if edge.startSketchPoint.geometry.isEqualTo(refPoint.geometry):
        return edge.startSketchPoint.geometry.vectorTo(edge.endSketchPoint.geometry)
    return edge.endSketchPoint.geometry.vectorTo(edge.startSketchPoint.geometry)
    

def isEdgeAssociatedWithFace(face:adsk.fusion.BRepFace, edge:adsk.fusion.BRepEdge):
    
    # have to check both ends - not sure which way around the start and end vertices are
    if (edge.startVertex in face.vertices 
        or edge.endVertex in face.vertices):
        return True
    return False
    
def getCornerEdgesAtFace(face:adsk.fusion.BRepFace, edge:adsk.fusion.BRepEdge)->Tuple[adsk.fusion.BRepEdge, adsk.fusion.BRepEdge]:
    '''
    With orthogonal corner edge to face, returns the two edges on the Face that meet at the corner
    '''
    #not sure which end is which - so test edge ends for inclusion in face
    startVertex = edge.startVertex if edge.startVertex in face.vertices else edge.endVertex 

    #edge has 2 adjacent faces - therefore the face that isn't from the 3 faces of startVertex, has to be the top face edges
#    returnVal = [edge1 for edge1 in edge.startVertex.edges if edge1 in face.edges]
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
    return edge.endVertex
    
def messageBox(*args):
    adsk.core.Application.get().userInterface.messageBox(*args)


def getTopFacePlane(faceEntity: adsk.fusion.BRepFace)->Tuple[adsk.core.Plane, adsk.fusion.BRepFace]:
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
    return (adsk.core.Plane.create(top.pointOnFace, getFaceNormal(top)), top)

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