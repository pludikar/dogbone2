import logging, sys, gc
import time
import adsk.core, adsk.fusion
from typing import ClassVar
from dataclasses import dataclass
import pprint
from functools import wraps

pp = pprint.PrettyPrinter()

logger = logging.getLogger('CustomPocket.decorators')
logger.setLevel(logging.DEBUG)

@dataclass
class HandlerContext():
    handler: adsk.core.Base
    event: adsk.core.Event


@dataclass
class HandlerCollection(HandlerContext):
    '''
    class to keep event handlers persistent
    It's not apparent if it's possible to figure which event each handler is attached to
    If you want to remove a handler selectively, you need both event and handler together.
    '''
    handlers: ClassVar = {}
    group: str = 'default'
    
    def __post_init__(self):
        try:
            HandlerCollection.handlers[self.group].append(HandlerContext(self.event, self.handler))
        except KeyError:
            HandlerCollection.handlers[self.group] = [HandlerContext(self.event, self.handler)]

    @classmethod
    def remove(cls, group):
        '''
        Simple remove of group key and its values - python GC will clean up any orphaned handlers
        If parameter is None then do a complete HandlerCollection reset
        '''
        if not group:
            cls.handlers = None
            return
        try:
            del cls.handlers[group]
        except KeyError:
            return

    # TODO - add selective eventHandler removal - might be more trouble than it's worth

# Decorator to add eventHandler
def eventHandler(handler_cls=adsk.core.Base):
    '''
    handler_cls is a subClass of EventHandler base class, which is not explicitly available.
    It must be user provided, and thus you can't declare the handler_cls to be of EventHandler type 
    EventHandler Classes such as CommandCreatedEventHandler, or MouseEventHandler etc. are provided to ensure type safety
    '''
    def decoratorWrapper(notify_method):
        @wraps(notify_method)  #spoofs wrapped method so that __name__, __doc__ (ie docstring) etc. behaves like it came from the method that is being wrapped.   
        def handlerWrapper( *handler_args, event=adsk.core.Event, group:str='default',**handler_kwargs):
            '''When called returns instantiated _Handler 
                - assumes that the method being wrapped comes from an instantiated Class method
                - inherently passes the "self" argument, if called method is in an instantiated class  
                - kwarg "event" throws an error if not provided '''

            logger.debug(f'notify method created: {notify_method.__name__}')

            try:

                class _Handler(handler_cls):

                    def notify( self, eventArgs):
                        try:
                            logger.debug(f'{notify_method.__name__} handler notified: {eventArgs.firingEvent.name}')
                            notify_method(*handler_args, eventArgs)  #notify_method_self and eventArgs come from the parent scope
                        except Exception as e:
                            print(e)
                            logger.exception(f'{eventArgs.firingEvent.name} error termination')
                h = _Handler() #instantiates handler with the arguments provided by the decorator
                event.add(h)  #this is where the handler is added to the event
                # HandlerCollection.handlers.append(HandlerCollection(h, event))
                HandlerCollection(group=group, handler=h, event=event)
                logger.debug(f'{pp.pformat(HandlerCollection.handlers)}')
                # adds to class handlers list, needs to be persistent otherwise GC will remove the handler
                # - deleting handlers (if necessary) will ensure that garbage collection will happen.
            except Exception as e:
                print(e)
                logger.exception(f'handler creation error')
            return h
        return handlerWrapper
    return decoratorWrapper

class Button(adsk.core.ButtonControlDefinition):
    def __init__():
        super().__init__()

    def addCmd(self, 
                parentDefinition, 
                commandId, 
                commandName, 
                tooltip, 
                resourceFolder,
                handlerMethod, 
                parentControl):
        commandDefinition_ = parentDefinition.itemById(commandId)

        if not commandDefinition_:
            commandDefinition_ = parentDefinition.addButtonDefinition(commandId, 
                                                                        commandName, 
                                                                        tooltip, 
                                                                        resourceFolder)
        
        handlerMethod(commandDefinition_.commandCreated)

        control_ = parentControl.addCommand(exportCommandDefinition_)
        exportControl_.isPromoted = True

        return commandDefinition_


def makeTempFaceVisible(method):
    @wraps(method)
    def wrapper (*args, **kwargs):

        # Create a base feature
        baseFeats = rootComp.features.baseFeatures
        baseFeat = baseFeats.add()
        
        baseFeat.startEdit()
        bodies = rootComp.bRepBodies

        tempBody = method(*args, **kwargs)
        tempBody.name = "Debug_" + method.__name__
        bodies.add(tempBody)

        baseFeat.finishEdit()
        return tempBody
    return wrapper

def entityFromToken(method):
    cacheDict = {}

    @wraps(method)
    def wrapper(*args, **kwargs):
        try:
            entityToken = method(*args, **kwargs)
            entity = cacheDict.setdefault(entityToken, design.findEntityByToken(entityToken)[0])
            return entity
        except:
            return None
    return wrapper

def tokeniseEntity(method):

    @wraps(method)
    def wrapper(*args, entity:adsk.core.Base = adsk.core.Base, **kwargs):
        '''
        Converts any entity passed in the parameters to its entityToken
        '''
        newArgs = []
        newkwargs = {}
        for a in args:
            try:
                newArgs.append(a.entityToken)
            except AttributeError:
                newArgs.append(a)
                continue
        for k, v in kwargs:
            try:
                newkwargs[k] = v.entityToken
            except AttributeError:
                newArgs[k] = v
                continue  
        result = method(*newArgs, **newkwargs)
        return result
    return wrapper


def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        startTime = time.time()
        result = func(*args, **kwargs)
        logger.debug('{}: time taken = {}'.format(func.__name__, time.time() - startTime))
        return result
    return wrapper     


    
     
        

 

    
     
        

 
