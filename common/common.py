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

RADIOBUTTONLIST_ID = 'dbButtonList' 
COMMAND_ID = "dogboneBtn"
EDIT_ID = "dogboneEditBtn"
FEATURE_ID = COMMAND_ID + 'Feature'

_app = adsk.core.Application.get()
_ui = _app.userInterface
_design = _app.activeProduct
_rootComp = _design.rootComponent

# get parent folder path
_appPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 

_customDogboneFeatureDef: adsk.fusion.CustomFeatureDefinition = None

