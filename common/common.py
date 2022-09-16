import logging
import adsk.fusion, adsk.core
import sys, os

FACE_ID = 'faceID'
REV_ID = 'revId'
ID = 'id'
DEBUGLEVEL = logging.NOTSET

NORMAL_MODE = 0x0
MINIMAL_MODE = 0x1
MORTISE_ALONG_LONGSIDE_MODE = 0x2
MORTISE_ALONG_SHORTSIDE_MODE = 0x4
FROMTOP_MODE = 0x8

RADIOBUTTONLIST_ID = 'seButtonList' 
COMMAND_ID = "scribeEdgeBtn"
EDIT_ID = "scribeEdgeEditBtn"
FEATURE_ID = COMMAND_ID + 'Feature'
NORMAL_ID = 'scribeEdgeNormalId'
MINIMAL_ID = 'scribeEdgeMinimalId'

_app = adsk.core.Application.get()
_ui = _app.userInterface
_design: adsk.fusion.Design = _app.activeProduct
_rootComp = _design.rootComponent

# get parent folder path
_appPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 

_customScribeEdgeFeatureDef: adsk.fusion.CustomFeatureDefinition = None

