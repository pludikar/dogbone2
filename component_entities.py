from . import root_entities as root
import adsk.core, adsk.fusion
import weakref
import logging

logger = logging.getLogger(__name__)

calcId = lambda x: str(x.tempId) + ":" + x.assemblyContext.name.split(":")[-1] if x.assemblyContext else str(x.tempId) + ":" + x.body.name




class CompBody(root.RootBody):
    """
    Object keeping data for Component Bodies
    """
    

    
    def __init__(self, parent, body:adsk.fusion.BRepBody):
        super().__init__(parent, body)
        logger.debug("adding compBody")
        self._isComponent = True
        self.id = str(body.tempId) + ':' + body.parentComponent.name
        return



class CompFace(root.RootFace):
    
    def __init__(self, parent, face):
        super().__init__(parent, face)
        self.faceId = str(face.tempId) + ":" + face.body.parentComponent.name
        pass

    def addEdge(self, edge):
        if edge.objectType != adsk.fusion.BRepEdge.classType():
            return False
        newEdge = CompEdge(self,edge)
        self.edges[newEdge.edgeId]
        return {self.faceId:newEdge}
        
       
class CompEdge(root.RootEdge):
    _parent = None
    edgeId = None
    
    def __init__(self, parent):
        self._parent = weakref.ref(parent)
        
