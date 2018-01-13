# dogbone2
#Author-Peter Ludikar
#Description-An Add-In for making dog-bone fillets.

This version is a proof of concept 

I've completely revamped the dogbone add-in by Casey Rogers and Patrick Rainsberry and David Liu
some of the original utilities have remained, but mostly everything else has changed.

The original add-in was based on creating points and extruding - I found using sketches and extrusion to be very heavy 
on processing resources, so this version has been designed to create dogbones directly by using a hole tool. So far the
the performance of this approach is day and night compared to the original version. 

Select the face you want the dogbones to drop from. Specify a tool diameter and a radial offset.
The add-in will then create a dogbone with diamater equal to the tool diameter plus
twice the offset (as the offset is applied to the radius) at each selected edge.

to do:
1. Improve the usability and speed
   Selection of multiple faces and selecting/deselecting target edges (intention is to use attributes to relate
   edges to faces, probably collected during onFaceSelect events - that way the prepopulated entities don't have to be 
   recalculated on every mouse move
2. ... who knows
