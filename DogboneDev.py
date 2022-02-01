#Author-Peter Ludikar, Gary Singer
#Description-An Add-In for making dog-bone fillets.

# Peter completely revamped the dogbone add-in by Casey Rogers and Patrick Rainsberry and David Liu
# Some of the original utilities have remained, but a lot of the other functionality has changed.

# The original add-in was based on creating sketch points and extruding - Peter found using sketches and extrusion to be very heavy 
# on processing resources, so this version has been designed to create dogbones directly by using a hole tool. So far the
# the performance of this approach is day and night compared to the original version. 

# Select the face you want the dogbones to drop from. Specify a tool diameter and a radial offset.
# The add-in will then create a dogbone with diamater equal to the tool diameter plus
# twice the offset (as the offset is applied to the radius) at each selected edge.

import logging
import os, sys
import adsk.core, adsk.fusion
import traceback

appPath = os.path.dirname(os.path.abspath(__file__))
# if appPath not in sys.path:
#     sys.path.insert(0, appPath)
if appPath+"\\py_packages" not in sys.path:
    sys.path.insert(0, appPath+"\\py_packages")

from .dbClasses.command import DogboneCommand
from .common import dbutils as util
from .common import decorators as d


logger = logging.getLogger('dogbone')

for handler in logger.handlers:
    handler.flush()
    handler.close()
    logger.removeHandler(handler)

formatter = logging.Formatter('%(asctime)s; %(name)s; %(levelname)s; %(lineno)d; %(funcName)s ; %(message)s')
logHandler = logging.FileHandler(os.path.join(appPath, 'dogbone.log'), mode='w')
logHandler.setFormatter(formatter)
logHandler.setLevel(logging.DEBUG)
logHandler.flush()
logger.addHandler(logHandler)
logger.setLevel(logging.DEBUG)


dog = DogboneCommand()


def run(context):
    try:
        logger.info('run - adding Command Button')
        dog.addButtons()
    except:
        util.messageBox(traceback.format_exc())


@d.clearDebuggerDict
def stop(context):
    try:
        logger.info('stop - removing Command Button')
        dog.removeButtons()
        adsk.terminate()
    except:
        util.messageBox(traceback.format_exc())

