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
        self.logger = logging.getLogger('dogbone.mgr'+self.__class__.__name__)

        self.register.add(self)

        self._entity = entity

        self._nativeObject = entity.nativeObject

        self._entityToken = entity.entityToken

        self._hash = hash(entity.entityToken)

        self._selected = False

        self._component_token = dbUtils.get_component_token(entity) if entity.assemblyContext else g._rootComp.entityToken

        self._temp_id = self._entity.tempId

        self._type: str


    def __hash__(self):
        return self._hash

    def __str__(self):
        name = self._entity.assemblyContext.name if self._entity.assemblyContext else self._entity.body.name
        return  f'{self._type}:{self._temp_id} - {name}' 

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._hash == other.__hash__

        if type(other) is int:
            return self._hash == other

        if type(other) is str:
            return (self.type_ == other 
                or self.entityToken == other
                or self.entity.body.entityToken == other
            )
        
        return NotImplemented
                
    def __del__(self):
        logger.debug(f"{self.__class__.__name__} deleted".format())
        self.register.remove(self)

    @property
    def entity(self):
        return self._entity

    @property
    def nativeObject(self):
        return self._nativeObject
        
    @property
    def component_hash(self):
        return hash(self._component_token)

    @property
    def component_token(self):
        return self._component_token

    @property
    def entity(self):
        return self._entity

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