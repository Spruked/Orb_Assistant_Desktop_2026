import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cali_skills.core.interface import CALISkill


@dataclass
class VoiceProfile:
    name: str
    voice_id: str
    character: str
    speed: float
    pitch: float
    emotion_profile: str
    sample_path: Optional[str] = None


class GoatSkill(CALISkill):
    """GOAT content engine for parsing, staging, and production routing."""

    def __init__(self, skill_id: str, config: Dict[str, Any]):
        super().__init__(skill_id, config)
        self.profiles_path = Path(__file__).resolve().parent / "profiles"
        self.staging_path = Path(__file__).resolve().parent / "staging"
        self.profiles_path.mkdir(parents=True, exist_ok=True)
        self.staging_path.mkdir(parents=True, exist_ok=True)
        self.characters = {
            "phil": VoiceProfile("Phil", "phil_v1", "Phil", 1.0, 1.0, "conversational"),
            "jim": VoiceProfile("Jim", "jim_v1", "Jim", 0.95, 0.9, "narrative"),
            "bryan": VoiceProfile("Bryan", "bryan_v1", "Bryan", 1.05, 1.1, "authoritative"),
            "narrator": VoiceProfile("Narrator", "narrator_v1", "Narrator", 1.0, 1.0, "neutral"),
        }

    def _load_metadata(self) -> Dict[str, Any]:
        return self.config

    def can_handle(self, intent: str, context: Dict[str, Any]) -> float:
        intent_lower = str(intent or "").lower()
        if any(character in intent_lower for character in ["phil", "jim", "bryan", "narrator"]):
            return 0.95
        if any(trigger in intent_lower for trigger in self.config.get("triggers", [])):
            return 0.92
        if any(item in intent_lower for item in ["book", "audiobook", "podcast", "narration", "script"]):
            return 0.85
        return 0.1

    def execute(self, command: str, params: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        try:
            dispatch = {
                "parse_content": self._parse_content,
                "create_voice_profile": self._create_voice_profile,
                "generate_narration": self._generate_narration,
                "create_audiobook_pipeline": self._create_audiobook_pipeline,
                "chunk_content": self._chunk_content,
                "apply_gravity_field": self._apply_gravity_field,
                "create_podcast_script": self._create_podcast_script,
                "export_audio": self._export_audio,
                "explain": self._explain,
                "locate_roots": self._locate_roots,
            }
            handler = dispatch.get(command)
            if not handler:
                return {"status": "error", "error": f"Unknown command: {command}", "confidence": 1.0}
            return handler(params or {})
        except Exception as exc:
            return {"status": "error", "error": str(exc), "command": command, "timestamp": datetime.utcnow().isoformat(), "confidence": 1.0}

    def _core_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "CALI_System" / "core_knowledge" / "goat_system"

    def _explain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        overview_path = self._core_path() / "overview.txt"
        overview = overview_path.read_text(encoding="utf-8", errors="replace").strip() if overview_path.exists() else "GOAT handles content preservation and production workflows."
        return {"status": "success", "result": overview, "confidence": 0.9}

    def _locate_roots(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._core_path() / "structure.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return {"status": "success", "result": data, "confidence": 0.85}

    def _parse_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        content = params.get("content", "")
        if params.get("file"):
            content = Path(params["file"]).expanduser().read_text(encoding="utf-8", errors="replace")
        structure = {
            "title": self._extract_title(content),
            "chapters": self._extract_chapters(content),
            "characters": self._detect_characters(content),
            "dialogue_segments": self._extract_dialogue(content),
            "word_count": len(content.split()),
            "estimated_duration": len(content.split()) / 150,
        }
        return {"status": "success", "structure": structure, "parsed_at": datetime.utcnow().isoformat(), "confidence": 0.9}

    def _extract_title(self, content: str) -> str:
        for line in content.strip().splitlines()[:5]:
            line = line.strip()
            if line.startswith("# "):
                return line[2:]
            if line:
                return line
        return "Untitled"

    def _extract_chapters(self, content: str) -> List[Dict[str, Any]]:
        pattern = r"(?:Chapter|CHAPTER)\s+(\d+|I{1,3}|IV|V|VI|VII|VIII|IX|X)|#{1,2}\s+(.+)"
        matches = list(re.finditer(pattern, content))
        if not matches:
            return [{"number": 1, "title": "Main Content", "start_pos": 0, "end_pos": len(content), "word_count": len(content.split())}]
        chapters = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            chapter_content = content[start:end]
            chapters.append({"number": index + 1, "title": match.group(1) or match.group(2) or f"Chapter {index + 1}", "start_pos": start, "end_pos": end, "word_count": len(chapter_content.split())})
        return chapters

    def _detect_characters(self, content: str) -> List[str]:
        matches = re.findall(r"([A-Z][a-zA-Z\s]{1,20})[:\s]*[\"']", content)
        return list(dict.fromkeys(match.strip() for match in matches))[:10]

    def _extract_dialogue(self, content: str) -> List[Dict[str, Any]]:
        segments = []
        for pattern in [r"\"([^\"]+)\"[,\s]*(?:said|cried|asked|replied)\s+([A-Z][a-z]+)", r"([A-Z][a-zA-Z\s]+):\s*\"([^\"]+)\""]:
            for match in re.finditer(pattern, content):
                left, right = match.group(1), match.group(2)
                speaker, text = (right, left) if pattern.startswith('"') else (left, right)
                segments.append({"speaker": speaker.strip(), "text": text.strip(), "position": match.start()})
        return segments

    def _create_voice_profile(self, params: Dict[str, Any]) -> Dict[str, Any]:
        character = str(params.get("character", "narrator")).lower()
        if character not in self.characters:
            return {"status": "error", "error": f"Unknown character: {character}", "confidence": 1.0}
        profile = self.characters[character]
        for key, value in params.get("settings", {}).items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile_file = self.profiles_path / f"{character}_profile.json"
        profile_file.write_text(json.dumps(profile.__dict__, indent=2), encoding="utf-8")
        return {"status": "success", "character": character, "profile": profile.__dict__, "saved_to": str(profile_file), "confidence": 0.95}

    def _generate_narration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        character = str(params.get("character", "narrator")).lower()
        profile_file = self.profiles_path / f"{character}_profile.json"
        profile = json.loads(profile_file.read_text(encoding="utf-8")) if profile_file.exists() else self.characters.get(character, self.characters["narrator"]).__dict__
        segment = {"text": params.get("text", ""), "speaker": character, "voice_settings": {"speed": profile.get("speed", 1.0), "pitch": profile.get("pitch", 1.0), "emotion": params.get("emotion", "neutral")}, "tts_engine": "kokoro", "estimated_duration": len(str(params.get("text", "")).split()) / 150}
        return {"status": "success", "segment": segment, "ready_for_synthesis": True, "confidence": 0.9}

    def _create_audiobook_pipeline(self, params: Dict[str, Any]) -> Dict[str, Any]:
        parsed = self._parse_content(params)
        if parsed["status"] != "success":
            return parsed
        structure = parsed["structure"]
        pipeline = {"project_id": f"goat_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "title": structure["title"], "stages": []}
        for chapter in structure["chapters"]:
            pipeline["stages"].append({"type": "chapter", "chapter_num": chapter["number"], "title": chapter["title"], "operations": [{"op": "chunk", "word_count": chapter["word_count"]}, {"op": "assign_voice", "default": "narrator"}, {"op": "tts_generate", "engine": "kokoro"}, {"op": "post_process", "normalize": True}]})
        pipeline_file = self.staging_path / f"{pipeline['project_id']}.json"
        pipeline_file.write_text(json.dumps(pipeline, indent=2), encoding="utf-8")
        return {"status": "success", "pipeline": pipeline, "total_chapters": len(structure["chapters"]), "estimated_total_duration": structure["estimated_duration"], "saved_to": str(pipeline_file), "next_step": "Execute pipeline with TTS engine", "confidence": 0.92}

    def _chunk_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        max_size = int(params.get("max_size", 4000))
        chunks, current = [], ""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if len(current) + len(sentence) < max_size:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return {"status": "success", "chunks": chunks, "count": len(chunks), "avg_size": sum(len(chunk) for chunk in chunks) / len(chunks) if chunks else 0, "confidence": 0.95}

    def _apply_gravity_field(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        field_strength = float(params.get("strength", 1.0))
        key_terms = params.get("key_terms", ["important", "critical", "remember", "key"])
        narration_marks = []
        for term in key_terms:
            for match in re.finditer(rf"([^.]*\b{re.escape(term)}\b[^.]*\.)", text, re.IGNORECASE):
                narration_marks.append({
                    "start": match.start(),
                    "end": match.end(),
                    "text": match.group(1).strip(),
                    "emphasis": True,
                    "pause_before_ms": int(250 * field_strength),
                    "pause_after_ms": int(180 * field_strength),
                })
        if field_strength > 1.0:
            speed = 0.9
        elif field_strength < 1.0:
            speed = 1.1
        else:
            speed = 1.0
        tts_parameters = {
            "engine": params.get("tts_engine", "kokoro"),
            "speed": speed,
            "pitch": 1.0,
            "emotion": params.get("emotion", "neutral"),
            "field_strength": field_strength,
            "supports_inline_markup": False,
        }
        return {
            "status": "success",
            "original_length": len(text),
            "modified_length": len(text),
            "field_strength": field_strength,
            "processed_text": text,
            "tts_parameters": tts_parameters,
            "narration_marks": narration_marks,
            "markers_added": len(narration_marks),
            "confidence": 0.9,
        }

    def _create_podcast_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        topic = params.get("topic", "General Discussion")
        segments = params.get("segments", [{"type": "intro", "duration": 30}, {"type": "banter", "characters": ["Phil", "Jim"], "duration": 120}, {"type": "content", "duration": 600}, {"type": "outro", "duration": 30}])
        script = {"show": "Phil and Jim Dandy Show", "episode_id": f"EP{datetime.utcnow().strftime('%Y%m%d')}", "topic": topic, "created_by": "GOAT System", "segments": []}
        for index, segment in enumerate(segments):
            script["segments"].append({"index": index, "type": segment["type"], "duration": segment.get("duration", 60), "content_outline": self._segment_outline(segment, topic), "voice_assignments": self._assign_podcast_voices(segment)})
        script_file = self.staging_path / f"{script['episode_id']}_script.json"
        script_file.write_text(json.dumps(script, indent=2), encoding="utf-8")
        total_duration = sum(segment.get("duration", 60) for segment in segments)
        return {"status": "success", "script": script, "total_duration_seconds": total_duration, "estimated_file_size_mb": (total_duration / 60) * 1.5, "saved_to": str(script_file), "confidence": 0.9}

    def _segment_outline(self, segment: Dict[str, Any], topic: str) -> str:
        return {"intro": f"Introduce show and topic: {topic}", "banter": "Casual conversation between Phil and Jim about recent events", "content": f"Deep dive into {topic} with examples and analysis", "outro": "Wrap up, call to action, sign-off"}.get(segment["type"], "General discussion")

    def _assign_podcast_voices(self, segment: Dict[str, Any]) -> List[str]:
        return {"banter": ["Phil", "Jim"], "intro": ["Phil"], "outro": ["Jim"]}.get(segment["type"], ["Narrator"])

    def _export_audio(self, params: Dict[str, Any]) -> Dict[str, Any]:
        quality = params.get("quality", "high")
        bitrate = {"low": "64k", "medium": "128k", "high": "192k"}.get(quality, "192k")
        export_settings = {
            "format": params.get("format", "mp3"),
            "bitrate": bitrate,
            "sample_rate": int(params.get("sample_rate", 22050)),
            "channels": int(params.get("channels", 2)),
            "normalize": bool(params.get("normalize", True)),
            "trim_silence": bool(params.get("trim_silence", True)),
        }
        cache_basis = json.dumps({
            "text": params.get("text") or params.get("input_text") or "",
            "source_path": params.get("source_path") or params.get("file") or "",
            "voice": params.get("voice") or params.get("character") or "narrator",
            "export_settings": export_settings,
        }, sort_keys=True)
        cache_key = hashlib.sha256(cache_basis.encode("utf-8")).hexdigest()[:24]
        audio_cache = self.staging_path / "audio_cache"
        audio_cache.mkdir(parents=True, exist_ok=True)
        target_audio_path = audio_cache / f"{cache_key}.{export_settings['format']}"
        return {
            "status": "success",
            "export_settings": export_settings,
            "cache_key": cache_key,
            "target_audio_path": str(target_audio_path),
            "cache_hit": target_audio_path.exists(),
            "post_processing": ["normalize_audio", "add_metadata_tags", "generate_waveform"],
            "confidence": 0.95,
        }

    def get_memory_scope(self) -> List[str]:
        return ["skills/goat", "voice_profiles", "content_cache", "production_history"]
