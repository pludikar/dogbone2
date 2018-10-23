# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion

import logging

calcId = lambda x: str(x.tempId) + ':' + x.assemblyContext.name.split(':')[-1] if x.assemblyContext else str(x.tempId) + ':' + x.body.name


class Model:
    
    bodies = []
    
    def __init__(self):
        return
        
        
    def addBody(self, body):
        if body.objectType != adsk.fusion.BRepBody.classType():
            return False
        newBody = Body(self,body)
        self.bodies.append(newBody)
        return newBody
        
        
class Body:
    
    faces = []
    parentObject = None
    body = None
    name = ""
    occurrence = None
    isComponent = None
    
    
    def __init__(self, parent, body):
        self.parent = parent
        self.body = body
        self.isComponent = True if body.assemblyContext else False
        self.name = body.assemblyContext.name if self.isComponent else body.name 
        return

    def addFace(self, face):
        if face.objectType != adsk.fusion.BRepFace.classType():
            return False
        newFace = Face(self, face)
        self.faces.append(newFace)
        return newFace
        
class Face:
    
    edges = []
    parentObject = None
    body = None
    entity = None
    faceId = None
    
    def __init__(self, parent, face):
        self.parent = parent
        self.body = parent.body
        self.entity = face
        self.faceId = (str(face.tempId) + ":" + face.assemblyContext.name.split(':')[-1]) if parent.isComponent else (face.body.name)
        
    def addEdge(self, edge):
        if edge.objectType != adsk.fusion.BRepEdge.classType():
            return False
        newEdge = Edge(self,edge)
        self.edges.append(newEdge)
        return newEdge
        
class Edge:
    
    def __init__(self, parent):
        self.parent = parent
        
    def parent(self):
        print (self.parent)
        
        
