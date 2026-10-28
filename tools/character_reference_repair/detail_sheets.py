"""Non-destructive inspection crops; source images and generation bytes stay intact."""
from PIL import Image, ImageOps, ImageDraw, ImageFont
from inventory import OUT, read, media

def sheet(key,items):
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    canvas=Image.new('RGB',(1500,((len(items)+2)//3)*640),'#18212c');d=ImageDraw.Draw(canvas)
    for i,(label,path) in enumerate(items):
        im=Image.open(media(path)).convert('RGB');w,h=im.size
        # A full-size centre crop retains source detail for the head, hands and legs.
        region=im.crop((int(w*.31),0,int(w*.69),h));region=ImageOps.contain(region,(490,600))
        x=(i%3)*500;y=(i//3)*640;canvas.paste(region,(x+(500-region.width)//2,y));d.text((x+5,y+605),label,font=font,fill='white')
    target=OUT/'inspect'/f'{key}.jpg';canvas.save(target,quality=97);print(target)

if __name__=='__main__':
 state=read(OUT/'run.json');items=[(k+' task'+str(v['id']),v['path']) for k,v in state['tasks'].items() if v.get('path')]
 for n in range(0,len(items),6):sheet('repairs-'+str(n//6+1),items[n:n+6])
