import logging
import adsk.core, adsk.fusion

import traceback
from functools import reduce

from ..common import dbutils as u
from .dbEntity import DbEntity
from .dbEdge import DbEdge

logger = logging.getLogger('dogbone.dbface')

class DbFace(DbEntity):
    """
    This class manages a single dogbone Face:
    keeps and makes a record of the viable edges, whether selected or not
    principle of operation: the first face added to a body/occurrence entity will find all other same facing faces, automatically finding eligible edges - they will all be selected by default.
    edges and faces have to be selected to be selected in the UI
    when all edges of a face have been deselected, the face becomes deselected
    when all faces of a body/entity have been deselected - the occurrence and all associated face and edge objects will be deleted and GC'd  (in theory)
    manages edges:
        edges can be selected or deselected individually
        faces can be selected or deselected individually
        first face selection will cause all other appropriate faces and corresponding edges on the body to be selected
        validEdges dict makes lists of candidate edges available
        each face or edge selection that is changed will reflect in the parent management object selectedOccurrences, selectedFaces and selectedEdges
    """

    def __init__(self, face):  #preload is used when faces are created from attributes.  preload will be a namedtuple of faceHash and occHash

        logger.info(f'---------------------------------creating face---------------------------')
        
        super().__init__(face)

        self.faceNormal = u.getFaceNormal(self._entity)
        
        self.topFacePlane, self.topFacePlaneHash = u.getTopFacePlane(face)
        
        logger.debug(f'{self._hash} - face initiated')           

        #==============================================================================
        #             this is where inside corner edges, dropping down from the face are processed
        #==============================================================================

    def __post__init__(self, face):
                
        self.brepEdges = u.findInnerCorners(face) #get all candidate edges associated with this face
        if not self.brepEdges:
            logger.debug('no edges found on selected face '.format(self.__hash__))
            self._selected = False
            return

        logger.debug('{} - edges found on face creation'.format(len(self.brepEdges)))
        for edge in self.brepEdges:
            if edge.isDegenerate:
                continue
            try:
                edgeObject = DbEdge(edge, self) #create a new edgeObject
                edgeObject.select()
                logger.debug(f' {edgeObject._hash} - edge object added')
    
            except:
                u.messageBox(f'Failed at edge:\n{traceback.format_exc()}')

        logger.debug(f'registered component count = {len(self.register.registeredObjectsAsList(DbFace) )}')

    def __iter__(self):
        for edge in self.register.registeredObjectsAsList(self, DbFace):
            yield edge

    def select(self):
        associatedEdges = self.register.registeredObjectsByParentAsList(DbEdge, self.entity)
        for edgeObject in associatedEdges:
            edgeObject.select()
        self._selected = True

    def deselect(self):
        associatedEdges = self.register.registeredObjectsByParentAsList(DbEdge, self.entity)
        for edgeObject in associatedEdges:
            edgeObject.deselect()
        self._select = False

