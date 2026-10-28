"""Independent scene-continuity run; shares only safe IO/SQL helpers."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('character_story_io',ROOT/'tools/character_story/setup.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
sha,write,mysql=helper.sha,helper.write,helper.mysql
DATA=ROOT.parent/'Data'
OUT=DATA/'CharacterScene20261027'
