"""Procedural COCO18 layout for two adults; no model inference or installation."""
import json
from PIL import Image,ImageDraw
from run import FOLDER

people=[
 [(438,135),(445,210),(395,222),(366,345),(360,462),(505,222),(535,350),(540,465),
  (411,450),(408,620),(402,800),(480,450),(490,620),(506,800),(426,126),(450,126),(417,137),(460,137)],
 [(1081,259),(1080,329),(1025,343),(1005,433),(1036,499),(1135,343),(1163,435),(1129,502),
  (1048,516),(1009,632),(1000,797),(1115,516),(1150,633),(1166,797),(1069,249),(1093,249),(1060,260),(1102,260)]
]
colors=[(255,0,0),(255,85,0),(255,170,0),(255,255,0),(170,255,0),(85,255,0),(0,255,0),(0,255,85),
 (0,255,170),(0,255,255),(0,170,255),(0,85,255),(0,0,255),(85,0,255),(170,0,255),(255,0,255),(255,0,170),(255,0,85)]
limbs=[(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(1,8),(8,9),(9,10),(1,11),(11,12),(12,13),(1,0),(0,14),(14,16),(0,15),(15,17)]
canvas=Image.new('RGB',(1536,864))
for points in people:
 for index,(a,b) in enumerate(limbs):
  layer=canvas.copy();ImageDraw.Draw(layer).line([points[a],points[b]],fill=colors[index],width=10)
  canvas=Image.blend(canvas,layer,.6)
 draw=ImageDraw.Draw(canvas)
 for (x,y),color in zip(points,colors):draw.ellipse((x-5,y-5,x+5,y+5),fill=color)
target=FOLDER/'two-person-pose.png'
if target.exists(): raise RuntimeError('Existing guide preserved')
canvas.save(target)
(FOLDER/'two-person-pose.json').write_text(json.dumps(dict(width=1536,height=864,bodyKeypoints=people,
 provenance='Procedural two-person COCO18 layout, not a generated image'),indent=2),encoding='utf-8')
