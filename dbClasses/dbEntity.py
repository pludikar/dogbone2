import logging
from shelve import Shelf
from ..common import dbutils as dbUtils
from .register import Register
from ..common import common as g

logger = logging.getLogger('dogbone.dbEntity')

class PostInitCaller(type):
    '''
    Overrides the class __call__ on instance creation with a standard __init__ followed by a __post__init__ 
    there's a dependency between edge and its parent, parent needs to be initialized fully before edges can be generated on faceObject creation
    '''
    def __call__(cls, *args, **kwargs):
        obj = type.__call__(cls, *args, **kwargs)
        try:
            obj.__post__init__( *args, **kwargs)
        except AttributeError:  #just in case __post__init__ isn't defined - eg in DbEdge
            pass
        return obj

class DbEntity(metaclass=PostInitCaller):
    '''
    Parent class representing the common attributes and methods for both faces and edges
    '''
    register = Register()
    _objectType: str
    
    def __init__(self, entity):
        self.logger = logging.getLogger(f'dogbone.mgr{self.__class__.__name__}')

        self.register.add(self)

        self._entity = entity


        self._entityToken = entity.entityToken

        self._hash = hash(entity.entityToken)

        self._selected = False

        self._body_token = entity.body.entityToken

        self._body_hash = hash(self._body_token)

        self._body_nativeObject_hash = hash(entity.body.nativeObject.entityToken) \
                                        if entity.body.assemblyContext else entity.body.entityToken

        self._component_hash = hash(entity.body.parentComponent.entityToken)

        # self._occurrence_hash = hash(entity.assemblyContext.entityToken) \
        #                         if entity.assemblyContext else hash(self.entity.body.entityToken)

        self._temp_id = self._entity.tempId

        self._type: str = None

    def __hash__(self):
        return self._hash

    def __str__(self):
        name = self._entity.assemblyContext.name if self._entity.assemblyContext else self._entity.body.name
        return  f'{self._type}:{self._temp_id} - {name}' 

    def __eq__(self, other):
        if isinstance(other, DbEntity):
            return self._hash == other._hash

        if type(other) == type(self.entity):
            return self.entity == other

        if type(other) is int:
            return (self._hash == other 
                or self._body_hash == other
                # or self._occurrence_hash == other
                or self._component_hash == other
                or self._body_nativeObject_hash == other)

        if type(other) is str:
            return (self._type == other 
                or self._entityToken == other
                or self._body_token == other
            )
        
        return NotImplemented
                
    def __del__(self):
        logger.debug(f"{self.__class__.__name__} deleted".format())
        self.register.remove(self)

    @property
    def entity(self):
        return self._entity

    @property
    def nativeObject_hash(self):
        return self._body_nativeObject_hash

    @property
    def occurrence_token(self):
        return self._occurrence_token
        
    @property
    def body_hash(self):
        return self._body_hash

    @property
    def body_token(self):
        return self._body_token

    # @property
    # def occurrence_hash(self):
    #     return self._occurrence_hash

    @property
    def component_hash(self):
        return self._component_hash

    @property
    def type_(self):
        return self._type

    @property
    def entityToken(self):
        return self._entityToken

    @property
    def isselected(self):
        return self._selected

    def select(self):
        self._selected = True
        return self._selected

    def deselect(self):
        self._selected = False
        return self._selected