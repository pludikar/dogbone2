from functools import reduce, lru_cache
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import List, ClassVar, Type
import adsk
class Register_meta

class Register:

    registerList: List = []

    @classmethod
    @lru_cache(maxsize=128)
    def getObject(cls, object:Type)->Type:  #needs hashable parameters in the arguments for lru_cache to work
        # cls.logger.debug('Entity Hash  = {}'.format(object))
        return  cls.registerList[object]

    @classmethod
    @lru_cache(maxsize=128)
    def isSelected(cls, object:Type)->Type:  #needs hashable parameters in the arguments for lru_cache to work
        # cls.logger.debug('Entity Hash  = {}'.format(object))
        return  cls.registerList[object].isSelected
   
    @classmethod
    @lru_cache(maxsize=128)
    def isSelectable(cls, object:Type)->Type:  #needs hashable parameters in the arguments for lru_cache to work
        # cls.logger.debug('Entity Hash  = {}'.format(object))
        if not len(cls.registerList):
            print('registerList = empty')
            return True
        return  object in cls.registerList[object]
  
    @classmethod
    @lru_cache(maxsize=128)
    def isFaceSelectable(cls, object:Type)->Type:  #needs hashable parameters in the arguments for lru_cache to work
        # cls.logger.debug('Entity Hash  = {}'.format(object))
        if not len(cls.registerList):
            print('registerList = empty')
            return True
        return  object in [face for face in cls.registerList if isinstance(face, FaceObject)]
        
    def remove(cls, object)->None:
        del cls.registerList[object]

    @classmethod
    @property        
    def registeredEdgeObjectsAsList(cls)->List[Type]:
        return [edge for edge in cls.registerList if isinstance(edge, EdgeObject)]

    @classmethod
    @property        
    def registeredFaceObjectsAsList(cls)->List[Type]:
        return [face for face in cls.registerList if isinstance(face, FaceObject)]
        
    @classmethod
    @property
    def registeredEntitiesAsList(cls)->List[adsk.fusion.BRepFace]:
        # cls.logger.debug('registeredEntitiesAsList')
        return [x.entity for x in cls.registerList]

    @classmethod
    @property
    def selectedEdgeObjectsAsList(cls):
        cls.logger.debug('selectedEdgesAsList')
        return [edge for edge in cls.registerList if isinstance(edge, EdgeObject) and edge.selected]
            
    @classmethod
    @property        
    def selectedFaceObjectsAsList(cls):
        cls.logger.debug('selectedFacesAsList')
        return [face for face in cls.registerList if isinstance(face, FaceObject) and face.selected]
                     
    @classmethod
    @property
    def registeredOccurrencesAsList(cls):
#TODO
        return set([x.occurence for x in cls.registerList])

@dataclass(init=False)
class FaceObject:
    def __init__(self,faceEntity: adsk.fusion.BRepFace):
        Register.registerList.append(self)

@dataclass(init=False)
class EdgeObject:
    def __init__(self,edgeEntity: adsk.fusion.BRepEdge):
        Register.registerList.append(self)
