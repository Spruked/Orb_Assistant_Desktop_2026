import asyncio
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

try:
    import aiohttp
except Exception:
    aiohttp = None

from cali_skills.core.interface import CALISkill


class ResearchSkill(CALISkill):
    """Agentic Research API Layer / Swarm Research Engine."""

    def __init__(self, skill_id: str, config: Dict[str, Any]):
        super().__init__(skill_id, config)
        self.cache_path = Path(__file__).resolve().parent / "cache"
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.cache_duration = timedelta(hours=24)
        self.sources = {
            "usda": "https://api.nal.usda.gov/fdc/v1",
            "sec_edgar": "https://www.sec.gov/Archives/edgar/daily-index",
            "census": "https://api.census.gov/data",
            "noaa": "https://api.weather.gov",
            "arxiv": "http://export.arxiv.org/api/query",
            "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            "data_gov": "https://catalog.data.gov/api/3",
        }

    def _load_metadata(self) -> Dict[str, Any]:
        return self.config

    def can_handle(self, intent: str, context: Dict[str, Any]) -> float:
        intent_lower = str(intent or "").lower()
        if any(source in intent_lower for source in ["usda", "sec", "edgar", "census", "noaa", "arxiv", "pubmed", "data.gov"]):
            return 0.95
        if any(trigger in intent_lower for trigger in self.config.get("triggers", [])):
            return 0.9
        if any(intent_lower.startswith(word) for word in ["what", "how", "why", "when", "where", "who", "which"]):
            return 0.7
        return 0.1

    def execute(self, command: str, params: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        try:
            dispatch = {
                "multi_source_query": lambda p: asyncio.run(self._multi_source_query(p)),
                "fetch_usda": lambda p: asyncio.run(self._fetch_usda(p)),
                "fetch_sec_edgar": lambda p: asyncio.run(self._fetch_sec_edgar(p)),
                "fetch_arxiv": lambda p: asyncio.run(self._fetch_arxiv(p)),
                "fetch_pubmed": lambda p: asyncio.run(self._fetch_pubmed(p)),
                "aggregate_results": self._aggregate_results,
                "verify_claim": lambda p: asyncio.run(self._verify_claim(p)),
                "explain": self._explain,
                "route": self._explain,
            }
            handler = dispatch.get(command)
            if not handler:
                return {"status": "error", "error": f"Unknown command: {command}", "confidence": 1.0}
            return handler(params or {})
        except Exception as exc:
            return {"status": "error", "error": str(exc), "command": command, "timestamp": datetime.utcnow().isoformat(), "confidence": 1.0}

    def _explain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success", "result": "Research skill performs browserless multi-source queries and routes to CALI substrate-first research when used through the desktop orb.", "confidence": 0.86}

    async def _multi_source_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query") or params.get("text") or ""
        sources = params.get("sources", ["arxiv", "pubmed"])
        max_results = int(params.get("max_results", 5))
        per_source_timeout = float(params.get("per_source_timeout", 5))
        queued_sources = []
        unsupported_sources = {}
        if aiohttp:
            async with aiohttp.ClientSession(headers={"User-Agent": "CALI-Orb-Research/3.0"}) as session:
                tasks = []
                for source in sources:
                    task = None
                    if source == "arxiv":
                        task = self._query_arxiv(session, query, max_results)
                    elif source == "pubmed":
                        task = self._query_pubmed(session, query, max_results)
                    elif source == "usda":
                        task = self._query_usda(session, query, max_results, params.get("api_key", "DEMO_KEY"))
                    else:
                        unsupported_sources[source] = {"source": source, "error": "unsupported source", "data": []}
                    if task:
                        queued_sources.append(source)
                        tasks.append(asyncio.wait_for(task, timeout=per_source_timeout))
                raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            raw_results = []
            for source in sources:
                queued_sources.append(source)
                raw_results.append(self._query_arxiv_sync(query, max_results) if source == "arxiv" else {"source": source, "error": "aiohttp unavailable", "data": []})
        aggregated = {"query": query, "sources_queried": sources, "results": dict(unsupported_sources), "total_findings": 0}
        for source, result in zip(queued_sources, raw_results):
            if isinstance(result, Exception):
                error = "source timed out" if isinstance(result, asyncio.TimeoutError) else str(result)
                aggregated["results"][source] = {"source": source, "error": error, "data": []}
            else:
                aggregated["results"][source] = result
                aggregated["total_findings"] += len(result.get("data", []))
        return {"status": "success", "research_data": aggregated, "synthesis_ready": True, "confidence": 0.85}

    async def _query_arxiv(self, session: Any, query: str, max_results: int) -> Dict[str, Any]:
        url = f"{self.sources['arxiv']}?search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}"
        async with session.get(url) as response:
            text = await response.text()
            if response.status != 200:
                return {"source": "arxiv", "error": f"HTTP {response.status}", "data": []}
        return self._parse_arxiv_feed(text, max_results)

    def _query_arxiv_sync(self, query: str, max_results: int) -> Dict[str, Any]:
        url = f"{self.sources['arxiv']}?search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}"
        with urllib.request.urlopen(url, timeout=12) as response:
            text = response.read().decode("utf-8", errors="replace")
        return self._parse_arxiv_feed(text, max_results)

    def _parse_arxiv_feed(self, text: str, max_results: int) -> Dict[str, Any]:
        entries = []
        try:
            root = ET.fromstring(text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:max_results]:
                title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
                summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
                paper_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
                entries.append({"title": " ".join(title.split()), "summary": " ".join(summary.split()), "id": paper_id, "url": paper_id})
        except Exception:
            titles = re.findall(r"<title>([^<]+)</title>", text)[1:]
            summaries = re.findall(r"<summary>([^<]+)</summary>", text)
            ids = re.findall(r"<id>([^<]+)</id>", text)
            for index in range(min(len(titles), max_results)):
                entries.append({"title": titles[index], "summary": summaries[index] if index < len(summaries) else "", "id": ids[index] if index < len(ids) else "", "url": ids[index] if index < len(ids) else ""})
        return {"source": "arxiv", "data": entries, "count": len(entries)}

    async def _query_pubmed(self, session: Any, query: str, max_results: int) -> Dict[str, Any]:
        search_url = f"{self.sources['pubmed']}/esearch.fcgi?db=pubmed&term={urllib.parse.quote(query)}&retmax={max_results}&retmode=json"
        async with session.get(search_url) as response:
            if response.status != 200:
                return {"source": "pubmed", "error": f"HTTP {response.status}", "data": []}
            data = await response.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return {"source": "pubmed", "data": [], "count": 0}
        summary_url = f"{self.sources['pubmed']}/esummary.fcgi?db=pubmed&id={','.join(idlist)}&retmode=json"
        async with session.get(summary_url) as response:
            if response.status != 200:
                return {"source": "pubmed", "error": f"HTTP {response.status}", "data": []}
            summary = await response.json()
        results = []
        for uid in idlist:
            info = summary.get("result", {}).get(uid, {})
            results.append({"title": info.get("title", "No title"), "authors": [a.get("name", "") for a in info.get("authors", [])], "id": uid, "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"})
        return {"source": "pubmed", "data": results, "count": len(results)}

    async def _query_usda(self, session: Any, query: str, max_results: int, api_key: str) -> Dict[str, Any]:
        url = f"{self.sources['usda']}/foods/search?query={urllib.parse.quote(query)}&pageSize={max_results}&api_key={api_key}"
        async with session.get(url) as response:
            if response.status != 200:
                return {"source": "usda", "error": f"HTTP {response.status}", "data": []}
            data = await response.json()
        results = []
        for food in data.get("foods", [])[:max_results]:
            results.append({"name": food.get("description"), "fdcId": food.get("fdcId"), "nutrients": [{"name": n.get("nutrientName"), "value": n.get("value"), "unit": n.get("unitName")} for n in food.get("foodNutrients", [])[:5]]})
        return {"source": "usda", "data": results, "count": len(results)}

    async def _fetch_usda(self, params: Dict[str, Any]) -> Dict[str, Any]:
        fdc_id = params.get("fdc_id")
        if not fdc_id:
            return {"status": "error", "error": "fdc_id required", "confidence": 1.0}
        if not aiohttp:
            return {"status": "missing_dependency", "error": "aiohttp is not installed", "confidence": 1.0}
        url = f"{self.sources['usda']}/food/{fdc_id}?api_key={params.get('api_key', 'DEMO_KEY')}"
        async with aiohttp.ClientSession(headers={"User-Agent": "CALI-Orb-Research/3.0"}) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return {"status": "success", "food_data": await response.json(), "source": "USDA FDC", "confidence": 0.95}
                return {"status": "error", "error": f"HTTP {response.status}", "confidence": 1.0}

    async def _fetch_sec_edgar(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cik = params.get("cik")
        if not cik:
            return {"status": "error", "error": "CIK required", "confidence": 1.0}
        if not aiohttp:
            return {"status": "missing_dependency", "error": "aiohttp is not installed", "confidence": 1.0}
        url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
        async with aiohttp.ClientSession(headers={"User-Agent": params.get("user_agent", "CALI Research Bot contact@example.com")}) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return {"status": "error", "error": f"HTTP {response.status}", "confidence": 1.0}
                data = await response.json()
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        indices = [i for i, form in enumerate(forms) if form == params.get("filing_type", "10-K")]
        results = [{"form": forms[i], "date": filings.get("filingDate", [])[i], "accessionNumber": filings.get("accessionNumber", [])[i]} for i in indices[:5]]
        return {"status": "success", "cik": cik, "filings": results, "confidence": 0.9}

    async def _fetch_arxiv(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if params.get("arxiv_id"):
            query_url = f"{self.sources['arxiv']}?id_list={urllib.parse.quote(str(params['arxiv_id']))}"
            text = urllib.request.urlopen(query_url, timeout=12).read().decode("utf-8", errors="replace")
            return {"status": "success", "paper_xml": text[:4000], "arxiv_id": params["arxiv_id"], "confidence": 0.95}
        return {"status": "success", **self._query_arxiv_sync(params.get("query", ""), 1), "confidence": 0.9}

    async def _fetch_pubmed(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not aiohttp:
            return {"status": "missing_dependency", "error": "aiohttp is not installed", "confidence": 1.0}
        pmid = params.get("pmid")
        if not pmid:
            result = await self._multi_source_query({"query": params.get("query", ""), "sources": ["pubmed"], "max_results": 1})
            return {"status": "success", "result": result, "confidence": 0.9}
        url = f"{self.sources['pubmed']}/efetch.fcgi?db=pubmed&id={pmid}&rettype=abstract"
        async with aiohttp.ClientSession(headers={"User-Agent": "CALI-Orb-Research/3.0"}) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return {"status": "success", "abstract_xml": (await response.text())[:4000], "pmid": pmid, "confidence": 0.95}
                return {"status": "error", "error": f"HTTP {response.status}", "confidence": 1.0}

    def _aggregate_results(self, params: Dict[str, Any]) -> Dict[str, Any]:
        results = params.get("results", {})
        query = params.get("query", "")
        synthesis = {"query": query, "timestamp": datetime.utcnow().isoformat(), "sources_used": list(results.keys()), "key_findings": [], "conflicts": [], "gaps": []}
        all_items = []
        for source, data in results.items():
            for item in data.get("data", []) if isinstance(data, dict) else []:
                all_items.append({"source": source, "title": item.get("title") or item.get("name") or "Untitled", "relevance": self._calculate_relevance(item, query), "citation": self._generate_citation(source, item)})
        all_items.sort(key=lambda item: item["relevance"], reverse=True)
        synthesis["key_findings"] = all_items[:10]
        return {"status": "success", "synthesis": synthesis, "top_result": all_items[0] if all_items else None, "confidence": 0.85}

    def _calculate_relevance(self, item: Dict[str, Any], query: str) -> float:
        title = str(item.get("title") or item.get("name") or "").lower()
        terms = [term for term in query.lower().split() if term]
        return min((sum(1 for term in terms if term in title) / max(1, len(terms))) * 1.5, 1.0)

    def _generate_citation(self, source: str, item: Dict[str, Any]) -> str:
        if source == "arxiv":
            return f"{item.get('title')}. arXiv: {item.get('id', '')}."
        if source == "pubmed":
            return f"{', '.join(item.get('authors', ['Unknown']))}. {item.get('title')}. PMID: {item.get('id')}"
        return f"{source}: {item.get('title') or item.get('name')}"

    async def _verify_claim(self, params: Dict[str, Any]) -> Dict[str, Any]:
        claim = params.get("claim", "")
        search = await self._multi_source_query({"query": claim, "sources": params.get("sources", ["arxiv", "pubmed"]), "max_results": 3})
        supporting = 0
        for data in search.get("research_data", {}).get("results", {}).values():
            for item in data.get("data", []) if isinstance(data, dict) else []:
                title = str(item.get("title", "")).lower()
                if all(term in title for term in claim.lower().split()[:3]):
                    supporting += 1
        verification = {"claim": claim, "sources_checked": params.get("sources", ["arxiv", "pubmed"]), "supporting_papers": supporting, "verification_status": "likely_true" if supporting > 0 else "unverified", "confidence": min(supporting * 0.3, 0.9)}
        return {"status": "success", "verification": verification, "evidence": search.get("research_data", {}), "confidence": verification["confidence"]}

    def get_memory_scope(self) -> List[str]:
        return ["skills/research", "research_cache", "source_index", "query_history"]
