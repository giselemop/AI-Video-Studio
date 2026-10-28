using System.Text;
using System.Text.Json;

namespace VideoStudio.Server;

/// <summary>A small authored instrumental preset; offline synthesis, not an AI music model.</summary>
public static class OriginalMusicService
{
    public const string Composition="window-warm-piano-v1";
    public const int SampleRate=24000;
    public const double DurationSeconds=15.5;

    public static bool Valid(JsonElement parameters)
        =>parameters.ValueKind==JsonValueKind.Object
          &&parameters.TryGetProperty("composition",out var c)&&c.ValueKind==JsonValueKind.String&&c.GetString()==Composition
          &&parameters.TryGetProperty("durationSeconds",out var d)&&d.TryGetDouble(out var duration)&&Math.Abs(duration-DurationSeconds)<.0001;

    public static async Task RenderAsync(string output,CancellationToken ct)
    {
        const double beat=60d/78d;
        var n=(int)(SampleRate*DurationSeconds);var left=new double[n];var right=new double[n];
        int[][] chords=[[48,55,60,64],[45,52,57,60],[41,48,53,57],[43,50,55,59],[48,55,60,64]];
        int[] arpeggio=[0,2,1,3,2,1,3,2];
        for(var bar=0;bar<chords.Length;bar++)
        {
            ct.ThrowIfCancellationRequested();var start=bar*4*beat;
            for(var voice=0;voice<4;voice++)Note(start,chords[bar][voice],Math.Min(3.4,DurationSeconds-start),.023,-.35+voice*.23,true);
            for(var i=0;i<8;i++)Note(start+i*beat/2,chords[bar][arpeggio[i]]+(i%4==3?12:0),1.8,.075,(i%3-1)*.35,false);
        }
        var melody=new (double Beat,int Midi,double Gain)[]{(0.5,72,.085),(2,76,.075),(3,79,.075),(4.8,76,.075),(6.2,72,.078),(7.5,69,.07),(8.7,69,.075),(10,72,.08),(11.4,76,.075),(12.6,74,.08),(14,71,.075),(15,72,.085),(17,76,.078),(18,79,.08),(19,72,.08)};
        foreach(var (when,midi,gain) in melody)Note(when*beat,midi,2.5,gain,.12,false);
        var delays=new[]{(int)(.17*SampleRate),(int)(.31*SampleRate),(int)(.53*SampleRate)};
        var wetL=(double[])left.Clone();var wetR=(double[])right.Clone();
        foreach(var delay in delays)for(var i=delay;i<n;i++){left[i]+=wetR[i-delay]*.12;right[i]+=wetL[i-delay]*.12;}
        var peak=Math.Max(left.Max(Math.Abs),right.Max(Math.Abs));var scale=peak>0?.70/peak:1;
        await using var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write,FileShare.None,65536,FileOptions.Asynchronous);
        using var writer=new BinaryWriter(stream,Encoding.ASCII,leaveOpen:true);
        writer.Write(Encoding.ASCII.GetBytes("RIFF"));writer.Write(36+n*4);writer.Write(Encoding.ASCII.GetBytes("WAVEfmt "));writer.Write(16);writer.Write((short)1);writer.Write((short)2);writer.Write(SampleRate);writer.Write(SampleRate*4);writer.Write((short)4);writer.Write((short)16);writer.Write(Encoding.ASCII.GetBytes("data"));writer.Write(n*4);
        for(var i=0;i<n;i++)
        {
            if((i&8191)==0)ct.ThrowIfCancellationRequested();
            var fade=Math.Min(1,Math.Min(i/(SampleRate*.5),(n-1-i)/(SampleRate*1.1)));
            writer.Write((short)Math.Clamp((int)(left[i]*scale*fade*32767),short.MinValue,short.MaxValue));
            writer.Write((short)Math.Clamp((int)(right[i]*scale*fade*32767),short.MinValue,short.MaxValue));
        }
        writer.Flush();await stream.FlushAsync(ct);

        void Note(double start,int midi,double length,double gain,double pan,bool pad)
        {
            var first=Math.Max(0,(int)(start*SampleRate));var end=Math.Min(n,first+(int)(length*SampleRate));var hz=440*Math.Pow(2,(midi-69)/12d);
            var l=Math.Sqrt((1-pan)/2);var r=Math.Sqrt((1+pan)/2);
            for(var i=first;i<end;i++)
            {
                var t=(i-first)/(double)SampleRate;var attack=Math.Min(1,t/(pad?.6:.012));
                var envelope=pad?attack*Math.Min(1,(end-i)/(SampleRate*.55)):attack*Math.Exp(-t*1.6);
                var phase=2*Math.PI*hz*t;
                var tone=pad?(Math.Sin(phase)*.8+Math.Sin(phase*2)*.12):(Math.Sin(phase)+.28*Math.Exp(-t*1.2)*Math.Sin(phase*2)+.12*Math.Exp(-t*2.1)*Math.Sin(phase*3)+.04*Math.Exp(-t*3)*Math.Sin(phase*4));
                var sample=tone*envelope*gain;left[i]+=sample*l;right[i]+=sample*r;
            }
        }
    }
}
