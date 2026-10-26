"""Extract ANSYS Fluent 2025 R2 Chinese UI terms for the Meshing contract."""

from __future__ import annotations

import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANSYS_ZH = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\fluent25.2.0\cortex\resources\language\zh"
)
LCONVERT = Path(r"D:\Ansys2025R2\ANSYS Inc\v252\tp\qt\5.15.18\winx64\bin\lconvert.exe")
CONTRACT = ROOT / "backend" / "app" / "meshing" / "workflow_schema.json"
OUTPUT = ROOT / "src" / "renderer" / "src" / "i18n" / "ansysZhTerms.ts"

MANUAL_TERMS = {
    "Yes": "是",
    "No": "否",
    "yes": "是",
    "no": "否",
    "All": "全部",
    "fluid": "流体",
    "solid": "固体",
    "dead": "死区域",
    "CAD": "CAD",
    "Mesh": "网格",
    "Single File": "单个文件",
    "Multiple Files": "多个文件",
    "Region Name": "区域名称",
    "Region Type": "区域类型",
    "Filter Text": "筛选文本",
    "File Format": "文件格式",
    "Import Type": "导入类型",
    "Units": "单位",
    "Use Body Labels": "使用几何体标签",
    "Advanced Options": "高级选项",
    "File Name": "文件名",
    "Size Control Type": "尺寸控制类型",
    "Name": "名称",
    "Target Mesh Size": "目标网格尺寸",
    "Growth Rate": "增长率",
    "Select By": "选择依据",
    "Labels": "标签",
    "Use Custom Size Field/Control Files?": "是否使用自定义尺寸场/控制文件？",
    "Minimum Size": "最小尺寸",
    "Maximum Size": "最大尺寸",
    "Size Functions": "尺寸函数",
    "Curvature Normal Angle [deg]": "曲率法向角 [度]",
    "Cells Per Gap": "每个间隙的单元数",
    "Scope Proximity To": "范围邻近",
    "Draw Size Boxes": "绘制尺寸框",
    "Separate out Boundary Zones by Angle?": "按角度分离边界区域？",
    "Geometry Type": "几何结构类型",
    "Add Boundary Layers?": "添加边界层？",
    "Offset Method Type": "偏移方法类型",
    "Number of Layers": "层数",
    "Transition Ratio": "过渡比",
    "Scope To": "范围",
    "Grow on": "在……上增长",
    "Fill With": "填充方法",
    "Solver": "求解器",
}

FORCED_TERMS = {
    "Body": "几何体",
    "Body Of Influence": "受影响的几何体",
    "Body Size": "几何体尺寸",
    "BodyLabelList": "几何体标签列表",
    "CompleteBLRegionList": "完整边界层区域列表",
    "CompleteBLZoneList": "完整边界层区域列表",
    "CompleteBlLabelList": "完整边界层标签列表",
    "CompleteEdgeLabelList": "完整边标签列表",
    "CompleteFaceLabelList": "完整面标签列表",
    "CompleteFaceZoneList": "完整面区域列表",
    "CompleteLabelSelectionList": "完整标签选择列表",
    "CompleteRegionScope": "完整区域范围",
    "CompleteTopologyList": "完整拓扑列表",
    "CompleteZoneSelectionList": "完整区域选择列表",
    "ConnectLabelWildcard": "连接标签通配符",
    "Face Of Influence": "受影响的表面",
    "Face Size": "面尺寸",
    "Fill Tetrahedral in Solids?": "在固体区域填充四面体？",
    "FluidLabelWildcard": "流体标签通配符",
    "HexMaxSize": "六面体最大尺寸",
    "IgnoreOrientation": "忽略方向",
    "Interface Connect": "交界面连接",
    "InvalidAdded": "添加无效项",
    "Join-Intersect": "连接-相交",
    "MaxSize": "最大尺寸",
    "OldRegionHexMaxCellLengthList": "旧区域六面体最大单元长度列表",
    "OldRegionNameList": "旧区域名称列表",
    "OldRegionTetGrowthRateList": "旧区域四面体增长率列表",
    "OldRegionTetMaxCellLengthList": "旧区域四面体最大单元长度列表",
    "OldRegionTypeList": "旧区域类型列表",
    "PrimeSizeControlId": "主尺寸控制 ID",
    "Program-controlled": "程序控制",
    "RegionCurrentList": "当前区域列表",
    "RegionCurrentTypeList": "当前区域类型列表",
    "RegionHexMaxCellLengthList": "区域六面体最大单元长度列表",
    "RegionHexNameList": "区域六面体名称列表",
    "RegionNameList": "区域名称列表",
    "RegionTetGrowthRateList": "区域四面体增长率列表",
    "RegionTetMaxCellLengthList": "区域四面体最大单元长度列表",
    "RegionTetNameList": "区域四面体名称列表",
    "RegionTypeList": "区域类型列表",
    "ShowSolidFluidMeshed": "显示已划分网格的固体/流体区域",
    "Stair Step": "阶梯",
    "Stair Step ICEMCFD Quality Limit": "ICEMCFD 阶梯质量限制",
    "all-zones": "所有区域",
    "non-conformal": "非共节点",
    "pyramids": "角锥体",
    "region": "区域",
    "region & angle": "区域与角度",
    "selected-labels": "所选标签",
    "selected-zones": "所选区域",
    "solid-fluid-interface": "固体-流体交界面",
    "_ ___ _______ _______________": "未命名参数",
    "_ _____ _____________ _____ _": "未命名参数",
    "_____ _____ _____ _____ _____": "未命名参数",
    "_________ ___ _ ___ _________": "未命名参数",
    "_______________ _______ ___ _": "未命名参数",
    "Import Geometry": "导入几何模型",
    "Add Local Sizing": "添加局部尺寸",
    "Generate the Surface Mesh": "生成表面网格",
    "Describe Geometry": "描述几何结构",
    "Update Regions": "更新区域类型设定",
    "Add Boundary Layers": "添加边界层",
    "Generate the Volume Mesh": "生成体网格",
    "Curvature & Proximity": "曲率与邻近",
    "Proximity": "邻近",
    "Multithreaded": "多线程",
    "Yes, size field file": "是，尺寸场文件",
    "Yes, size control file": "是，尺寸控制文件",
    "Yes, both files": "是，两个文件",
    "polyhedra": "多面体",
    "poly-hexcore": "多面体-六面体核心",
    "hexcore": "六面体核心",
    "tetrahedral": "四面体",
    "only-walls": "仅壁面",
    "fluid-regions": "流体区域",
    "solid-regions": "固体区域",
    "named-regions": "命名区域",
    "label": "标签",
    "zone": "区域",
    "body": "几何体",
    "face": "面",
    "edges": "边",
    "faces": "面",
    "faces-and-edges": "面和边",
    "aspect-ratio": "纵横比",
    "last-ratio": "最后纵横比",
    "uniform": "均匀",
    "smooth-transition": "平滑过渡",
    "no, use re-faceting": "否，使用重新小面化",
    "yes, using prism control file": "是，使用棱柱控制文件",
}


def _relevant_terms() -> list[str]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    terms = set(MANUAL_TERMS)
    for step in contract.get("steps") or []:
        terms.add(str(step.get("english_name")))
        for field in step.get("fields") or []:
            terms.add(str(field.get("label")))
            for value in field.get("enum") or []:
                if isinstance(value, str):
                    terms.add(value)
        toggle = step.get("toggle_field") or {}
        if toggle.get("label"):
            terms.add(str(toggle["label"]))
        for value in toggle.get("enum") or []:
            if isinstance(value, str):
                terms.add(value)
    return sorted(term for term in terms if term)


def _parse_ts(path: Path) -> list[tuple[str, str]]:
    root = ET.parse(path).getroot()
    pairs: list[tuple[str, str]] = []
    for message in root.findall(".//message"):
        source = message.findtext("source") or ""
        translation = message.findtext("translation") or ""
        if source and translation and source != translation:
            pairs.append((source, translation))
    return pairs


def main() -> int:
    terms = _relevant_terms()
    relevant = set(terms)
    files = sorted(ANSYS_ZH.glob("*.qm"))
    translations: dict[str, Counter[str]] = defaultdict(Counter)
    with tempfile.TemporaryDirectory(prefix="fluent-ansys-zh-") as temp:
        temp_dir = Path(temp)
        batch_size = 40
        for index in range(0, len(files), batch_size):
            batch = files[index : index + batch_size]
            output = temp_dir / f"batch-{index // batch_size}.ts"
            command = [str(LCONVERT)]
            for source in batch:
                command.extend(["-i", str(source)])
            command.extend(["-o", str(output)])
            subprocess.run(command, check=True, capture_output=True)
            for source, translation in _parse_ts(output):
                if source in relevant:
                    translations[source][translation] += 1

    resolved: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    missing: list[str] = []
    for term in terms:
        variants = translations.get(term)
        if variants:
            options = variants.most_common()
            resolved[term] = options[0][0]
            if len(options) > 1:
                conflicts[term] = [value for value, _count in options]
        elif term in MANUAL_TERMS:
            resolved[term] = MANUAL_TERMS[term]
        elif term in FORCED_TERMS:
            resolved[term] = FORCED_TERMS[term]
        else:
            missing.append(term)
    for term, translation in MANUAL_TERMS.items():
        resolved.setdefault(term, translation)
    resolved.update(FORCED_TERMS)

    lines = [
        "// Generated from ANSYS Fluent 2025 R2 Chinese .qm resources.",
        "export const ansysZhTerms: Record<string, string> = {",
    ]
    for source in sorted(resolved):
        lines.append(
            f"  {json.dumps(source, ensure_ascii=False)}: {json.dumps(resolved[source], ensure_ascii=False)},"
        )
    lines.extend(["}", "", "export const ansysZhMissingTerms = ["])
    for source in missing:
        lines.append(f"  {json.dumps(source, ensure_ascii=False)},")
    lines.extend(
        [
            "] as const",
            "",
            "export const ansysZhConflicts: Record<string, string[]> = "
            + json.dumps(conflicts, ensure_ascii=False, indent=2),
            "",
        ]
    )
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"terms={len(resolved)} missing={len(missing)} conflicts={len(conflicts)}")
    print(f"output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
