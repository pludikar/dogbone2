import logging
from functools import reduce, lru_cache
from typing import List
import json
import adsk.core, adsk.fusion
from pydantic.fields import T
from ..common import dbutils as u
from ..common.decorators import tokeniseEntity
from ..common import common as g

logger = logging.getLogger('dogbone.register')

class Register:

    registerList: List = []

    def __init__(self):
        pass

    def add(self, entity_object):
        Register.registerList.append(entity_object)

    def clear(self):
        for edgeObject in self.registeredEdgesAsList:
            del edgeObject
        for faceObject in self.registeredFacesAsList:
            del faceObject

    def resetCache(self):
        self.getobject.lru_cache.clear()
        self.isEntitySelectable.lru_cache.clear()
        # self.isselected.lru_cache.clear()
        # self.isOccurrenceRegistered.lru_cache.clear()
        # self.isEntitySelectable.lru_cache.clear()
        # self.isSelectable.lru_cache.clear()
        # self.selectedEdgesByParentAsList.lru_cache.clear()


    @tokeniseEntity
    def remove(self, objectHash:int)->None:
        try:
            # self.resetCache()
            Register.registerList.remove(objectHash)
        except ValueError:
            return False

    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def getobject(self, tokenOrObject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        try:
            return  Register.registerList[Register.registerList.index(tokenOrObject)]
        except ValueError:
            return False

    # @lru_cache(maxsize=128)
    def isSelected(self, dbobject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        return  Register.registerList[dbobject].isSelected

    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def isEntitySelectable(self, entity_token )->bool:  
        #needs hashable parameters in the arguments for lru_cache to work
        '''
        Checks if an entity is selectable 
        - return True if entity is already registered 
        otherwise check if it's an unregistered body inside a component (inc. root) 
        '''
        if entity_token in Register.registerList:
            return True  #entity is definitely in the register - so we can select it

        entity = g._design.findEntityByToken(entity_token)[0]
        # entity maybe associated with a body
        # if it's a body in the same occurrence then it can't be selected 
        if entity.assemblyContext:  #
            return hash(entity.body.nativeObject.entityToken) not in Register.registerList

        # now left with only needing to check if rootComponent body is in the register
        return hash(entity.body.entityToken) not in Register.registerList
    
    @property
    def asDict(self)->dict:
        '''
        Returns nested dict of each body, selected faces and associated edges
        '''
        return {bodyhash:\
            {face.entityToken: [edge.entityToken for edge in self.selectedEdgesByParentAsList(face)]\
                for face in self.selectedFacesByBodyAsList(bodyhash)}\
            for bodyhash in self.registeredOccurrenceHashesAsList }


# Cached properties - need to be cleared if registerList changes --------------------------------------

#TODO make caching strategy mores selective!!
#TODO weed out methods that aren't being used

    @property
    def topFacesByBodyasDict(self)->dict:
        '''
        Returns nested dict of each body, selected faces and associated edges
        '''
        return {body_token:list({face.topFaceEntity.entityToken 
                    for face in self.registeredFacesByBodyAsList(body_token)})
                    for body_token in self.registeredBodyTokensAsList}

    @tokeniseEntity
    def selectedgesByBodyAsTokenList(self, body_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and body_hash 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'edge' and obj.body_hash == body_hash and obj.isselected ]
    
    @tokeniseEntity
    def selectedFacesByBodyAsTokenList(self, body_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and body_hash 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'face' and obj.body_hash == body_hash  and obj.isselected ]

    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def selectedgesByParentAsList(self, parentToken: object )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and parent
        is Only applicable to cls = DbEdge 
        '''
        #ideally should have been filtered by DbEdge, but that makes Register more coupled than I wanted
        ojectList = [obj for obj in Register.registerList \
                        if (obj == 'edge'
                            and obj.parent == parentToken
                            and obj.isselected)]
        return ojectList

    @tokeniseEntity
    def selectedgesByBodyAsList(self, body_token: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and body_hash 
        '''
        body_hash = hash(body_token) 
        return [obj for obj in Register.registerList if obj == 'edge' and obj.body_hash == body_hash and obj.isselected ]

    @tokeniseEntity
    def selectedgesByFaceAsList(self, face_token: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and body_hash 
        '''
        face_hash = hash(face_token) 
        return [obj for obj in Register.registerList 
                    if obj == 'edge' and obj._hash == face_hash and obj.isselected ]
    
    @tokeniseEntity
    def selectedFacesByBodyAsList(self, body_token: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and body_hash 
        '''
        body_hash = hash(body_token) 
        return [obj for obj in Register.registerList if obj == 'face' and obj.body_hash == body_hash  and obj.isselected ]

    # @tokeniseEntity
    # @lru_cache(maxsize=128)
    def registeredEdgesByParentAsList(self, parentToken: object )->List[object]:
        '''
        returns list of objects filtered by edge and parent
        '''
        #ideally should have been filtered by DbEdge, but that makes Register more coupled than I wanted
        fullOjectList = [obj for obj in Register.registerList if obj == 'edge' and obj.parent == parentToken]
        return fullOjectList

    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def isOccurrenceRegistered(self, body_token)->bool:
        '''
        Returns if an entity has been registered 
        '''
        return body_token in list(set(obj.occurrence_token for obj in self.registerList))

    @tokeniseEntity
    def registeredEdgesByBodyAsList(self, body_token: int )->List[object]:
        '''
        returns list of objects filtered by edge and body_token 
        '''
        return [obj for obj in Register.registerList if obj == 'edge' and obj.body_token == body_token ]

    @tokeniseEntity
    def registeredFacesByBodyAsList(self, body_token: int )->List[object]:
        '''
        returns list of objects filtered by face and body_token 
        '''
        return [obj for obj in Register.registerList if obj == 'face' and obj.body_token == body_token ]

# looup properties below this line - many will be children of the cached properties above this
# ---------------------------------------------------------------------
    @property
    def selectedgesAsTokenList(self)->List[object]:
        '''
        returns list of entityTokens filtered by type (dbFace or dbEdge) 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'edge' and obj.isselected ]
    
    @property
    def selectedFacesAsTokenList(self)->List[object]:
        '''
        returns list of entityTokens filtered by type (dbFace or dbEdge) 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'face' and obj.isselected ]

    @property
    def allSelectedAsTokenList(self)->List[object]:
        '''
        returns list of entityTokens filtered by type (dbFace or dbEdge) 
        '''
        return [obj.entityToken for obj in Register.registerList if obj.isselected ]

    @property
    def allSelectedAsEntityList(self)->List[object]:
        '''
        returns list of entityTokens filtered by type (dbFace or dbEdge) 
        '''
        return [obj.entity for obj in Register.registerList if obj.isselected ]

    @property
    def selectedgesAsList(self)->List[object]:
        '''
        returns list of selected objects filtered by edge 
        '''
        return [obj for obj in Register.registerList if obj == 'edge' and obj.isselected ]
    
    @property
    def selectedFacesAsList(self)->List[object]:
        '''
        returns list of selected face objects 
        '''
        return [obj for obj in Register.registerList if obj == 'face' and obj.isselected ]

    @property
    def registeredFacesAsList(self)->List[object]:
        '''
        returns full list of registered face objects 
        '''
        return [obj for obj in Register.registerList if obj == 'face']
    
    @property
    def registeredEdgesAsList(self )->List[object]:
        '''
        returns full list of registered edge objects 
        '''
        return [obj for obj in Register.registerList if obj == 'edge']

    @property
    def registeredEntitiesAsList(self)->List[adsk.fusion.BRepFace]:
        '''
        Returns a full list of entities (BrepFaces and BrepEdges) that have been registered
        '''
        return [x.entity for x in Register.registerList]
    
    @property
    def registeredBodyTokensAsList(self):
        '''
        Returns a list of unique Body tokens 
        '''
        return list({obj._body_token for obj in self.registerList})

    @property
    def registeredBodyEntitiesAsList(self):
        ''' returns list of registered body entities'''
        return [g._design.findEntityByToken(token)[0] for token in self.registeredBodyTokensAsList]       

    @property
    def registeredOccurrenceEntitiesAsList(self):
        '''
        Returns a list of unique Body entities 
        '''
        def substituteIfRoot(token):
            try:
                return(g._design.findEntityByToken(token)[0]).assemblyContext.entityToken
            except IndexError:
                return None
        return [occurrenceToken for occurrenceToken in [substituteIfRoot(token) for token in self.registeredBodyTokensAsList] if not occurrenceToken]

    @property
    def registeredOccurrenceTokensAsList(self):
        '''
        Returns a list of unique Body tokens 
        '''
        return list({obj._component_token for obj in self.registerList})

    @property
    def registeredComponentEntitiesAsList(self):
        '''
        Returns a list of unique Component tokens 
        '''
        def substituteIfRoot(token):
            try:
                return(g._design.findEntityByToken(token)[0])
            except IndexError:
                return g._rootComp
        return [substituteIfRoot(token) for token in self.registeredComponentTokensAsList]