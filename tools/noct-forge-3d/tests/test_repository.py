import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "forge-3d-animation",
    "forge-3d-export",
    "forge-3d-manual-edits",
    "forge-3d-orchestrator",
    "forge-3d-model",
    "forge-3d-visual-conformance",
    "forge-3d-texture",
    "forge-3d-visualize",
    "forge-3d-setup",
}



class RepositoryTests(unittest.TestCase):
    def test_model_rule_sets_are_concise_markdown(self):
        found = {path.name for path in (ROOT / "model-rules").glob("*.md")}
        self.assertEqual(found, {"hytale.md", "minecraft-bedrock.md", "chibi.md"})
        for path in (ROOT / "model-rules").glob("*.md"):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# "))
                self.assertLess(len(text.splitlines()), 80)

    def test_skill_frontmatter_in_canonical_directory(self):
        skill_root = ROOT / ".agents" / "skills"
        found = {path.name for path in skill_root.iterdir() if path.is_dir()}
        self.assertEqual(found, SKILLS)
        for name in SKILLS:
            path = skill_root / name / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            match = re.match(r"^---\nname:\s*([^\n]+)\ndescription:\s*([^\n]+)\n---\n", text)
            self.assertIsNotNone(match, path)
            self.assertEqual(match.group(1).strip(), name)
            self.assertGreater(len(match.group(2).strip()), 20)
        self.assertFalse((ROOT / "skills").exists())

    def test_code_modeler_mode_references(self):
        names = {"shapes.md", "custom-mesh.md", "rigging.md", "placement-and-mirror.md",
                 "errors.md", "box-modeling.md"}
        source = ROOT / ".agents" / "skills" / "forge-3d-model" / "references"
        self.assertEqual({path.name for path in source.glob("*.md")}, names)
        skill = (ROOT / ".agents" / "skills" / "forge-3d-model" / "SKILL.md").read_text(encoding="utf-8")
        for name in names:
            self.assertIn(name, skill)

    def test_runnable_doc_examples_execute(self):
        """Every ```python block whose first line is '# runnable...' must run."""
        import re
        skills = ROOT / ".agents" / "skills"
        blocks = []
        for path in sorted(skills.rglob("*.md")):
            for code in re.findall(r"```python\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
                if code.lstrip().startswith("# runnable"):
                    blocks.append((path.name, code))
        self.assertGreaterEqual(len(blocks), 2)
        for name, code in blocks:
            with self.subTest(doc=name):
                namespace = {}
                exec(compile(code, name, "exec"), namespace)
                builder = namespace["builder"]
                self.assertEqual(builder.validate()["errors"], [])

    def test_shared_contract_docs_and_skill_references_are_available(self):
        self.assertTrue((ROOT / "docs/pipeline.md").is_file())
        tex_refs = ROOT / ".agents" / "skills" / "forge-3d-texture" / "references"
        self.assertEqual({path.name for path in tex_refs.glob("*.md")},
                         {"texture-painter-api.md", "fractional-uv.md", "art-requests.md", "procedural-fields.md",
                          "lineart.md", "render-modes.md", "theme.md", "uv-recipes.md"})
        vis_refs = ROOT / ".agents" / "skills" / "forge-3d-visualize" / "references"
        self.assertEqual({path.name for path in vis_refs.glob("*.md")},
                         {"viewer-api.md"})
        self.assertFalse((ROOT / ".agents" / "skills" / "forge-3d-visual-conformance" / "references").exists())
        self.assertFalse((ROOT / "Tools" / "TexturePainter" / "README.md").exists())

    def test_current_documentation_local_links_resolve(self):
        sources = [ROOT / "README.md", ROOT / "AGENTS.md", *(ROOT / "docs").glob("*.md"),
                   *(ROOT / ".agents/skills").rglob("*.md")]
        for source in sources:
            for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", source.read_text(encoding="utf-8")):
                target = target.strip("<>").split("#", 1)[0]
                if not target or re.match(r"[a-zA-Z]+:", target):
                    continue
                with self.subTest(source=source, target=target):
                    self.assertTrue((source.parent / target).exists())



if __name__ == "__main__":
    unittest.main()
