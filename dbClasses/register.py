import logging
from functools import reduce, lru_cache
from typing import List
import json
import adsk.core, adsk.fusion
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
        Register.registerList = []

    @tokeniseEntity
    def remove(self, objectHash:int)->None:
        try:
            Register.registerList.remove(objectHash)
        except ValueError:
            return False

    # @lru_cache(maxsize=128)
    @tokeniseEntity
    def getobject(self, tokenOrObject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        try:
            return  Register.registerList[Register.registerList.index(tokenOrObject)]
        except ValueError:
            return False

    # @lru_cache(maxsize=128)
    def isSelected(self, dbobject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        return  Register.registerList[dbobject].isSelected
    
    # @lru_cache(maxsize=128)
    def isSelectable(self, dbobject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        if not len(Register.registerList):
            return True
        return  Register.registerList[dbobject]
    
    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def isEntitySelectable(self, objectToken:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        '''
        Checks if an entity is selectable - should return True is entity is already registered
        '''
        objectHash = hash(objectToken)
        component_hash = hash(u.get_component_token(objectToken))

        if not self.isOccurrenceRegistered(component_hash):
            return True
        result = objectHash in Register.registerList
        return  result
    
    @property
    def asDict(self)->dict:
        '''
        Returns nested dict of each component, selected faces and associated edges
        '''
        return {componenthash:\
            {face.entityToken: [edge.entityToken for edge in self.selectededEdgesByParentAsList(face)]\
                for face in self.selectedFacesByComponentAsList(componenthash)}\
            for componenthash in self.registeredOccurrenceHashesAsList }

    @tokeniseEntity
    def selectedEdgesAsTokenList(self)->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'edge' and obj.isselected ]
    
    @tokeniseEntity
    def selectedFacesAsTokenList(self)->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'face' and obj.isselected ]

    @tokeniseEntity
    def selectedEdgesByComponentAsTokenList(self, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'edge' and obj.component_hash == component_hash and obj.isselected ]
    
    @tokeniseEntity
    def selectedFacesByComponentAsTokenList(self, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj.entityToken for obj in Register.registerList if obj == 'face' and obj.component_hash == component_hash  and obj.isselected ]

    @tokeniseEntity
    def selectedEdgesAsList(self)->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'edge' and obj.isselected ]
    
    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def selectededEdgesByParentAsList(self, parentToken: object )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and parent
        is Only applicable to cls = DbEdge 
        '''
        #ideally should have been filtered by DbEdge, but that makes Register more coupled than I wanted
        fullOjectList = [obj for obj in Register.registerList if obj == 'edge' and obj.parent == parentToken and obj.isselected]
        return fullOjectList
    
    @tokeniseEntity
    def selectedFacesAsList(self)->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'face' and obj.isselected ]


    @tokeniseEntity
    def selectedEdgesByComponentAsList(self, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'edge' and obj.component_hash == component_hash and obj.isselected ]
    
    @tokeniseEntity
    def selectedFacesByComponentAsList(self, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'face' and obj.component_hash == component_hash  and obj.isselected ]

    def registeredFacesAsList(self)->List[object]:
        '''
        returns full list of objects filtered by type (dbFace or dbEdge) 
        '''
        return [obj for obj in Register.registerList if obj == 'face']
    
    @tokeniseEntity
    def registeredEdgesAsList(self )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'edge']

    @tokeniseEntity
    def registeredFacesAsList(self)->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'face']

    @tokeniseEntity
    def registeredEdgesByComponentAsList(self, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if obj == 'edge' and obj.component_hash == component_hash ]

    @tokeniseEntity
    def registeredFacesByComponentAsList(self, component_token: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_token 
        '''
        return [obj for obj in Register.registerList if obj == 'face' and obj.component_token == component_token ]

    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def registeredEdgesByParentAsList(self, parentToken: object )->List[object]:
        '''
        returns list of objects filtered by edge and parent
        '''
        #ideally should have been filtered by DbEdge, but that makes Register more coupled than I wanted
        fullOjectList = [obj for obj in Register.registerList if obj == 'edge' and obj.parent == parentToken]
        return fullOjectList
    
    @property
    def registeredEntitiesAsList(self)->List[adsk.fusion.BRepFace]:
        '''
        Returns a full list of entities (BrepFaces and BrepEdges) that have been registered
        '''
        return [x.entity for x in Register.registerList]
    
    @property
    def registeredComponentTokensAsList(self):
        '''
        Returns a list of unique Component tokens 
        '''
        return list(set([obj._component_token for obj in self.registerList]))

    @property
    def registeredComponentEntitiesAsList(self):
        '''
        Returns a list of unique Component entities 
        '''
        def substituteIfRoot(token):
            try:
                return(g._design.findEntityByToken(token)[0])
            except IndexError:
                return g._rootComp
        return [substituteIfRoot(token) for token in self.registeredComponentTokensAsList]

    @property
    def registeredComponentHashesAsList(self):
        '''
        Returns a list of unique Component tokens 
        '''
        return [hash(token) for token in self.registeredComponentTokensAsList]
   
    @tokeniseEntity
    # @lru_cache(maxsize=128)
    def isOccurrenceRegistered(self, component_hash)->bool:
        '''
        Returns if an entity has been registered 
        '''
        return component_hash in list(set(obj.component_hash for obj in self.registerList))