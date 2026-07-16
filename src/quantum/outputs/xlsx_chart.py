from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from xml.sax.saxutils import escape as xml_escape


@dataclass(frozen=True, slots=True)
class ChartSpec:
    title: str
    categories: tuple[str, ...]
    values: tuple[Decimal, ...]
    from_col: int = 9
    from_row: int = 3
    to_col: int = 17
    to_row: int = 21


def chart_xml(spec: ChartSpec) -> bytes:
    category_points = "".join(
        f'<c:pt idx="{index}"><c:v>{xml_escape(value)}</c:v></c:pt>'
        for index, value in enumerate(spec.categories)
    )
    value_points = "".join(
        f'<c:pt idx="{index}"><c:v>{format(value, "f")}</c:v></c:pt>'
        for index, value in enumerate(spec.values)
    )
    title = xml_escape(spec.title)
    xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<c:date1904 val="0"/><c:lang val="ru-RU"/><c:roundedCorners val="0"/>
<c:chart>
<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="ru-RU" sz="1200" b="1"/><a:t>{title}</a:t></a:r><a:endParaRPr lang="ru-RU"/></a:p></c:rich></c:tx><c:layout/><c:overlay val="0"/></c:title>
<c:autoTitleDeleted val="0"/>
<c:plotArea><c:layout/>
<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="1"/>
<c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:v>Сумма, ₽</c:v></c:tx>
<c:cat><c:strLit><c:ptCount val="{len(spec.categories)}"/>{category_points}</c:strLit></c:cat>
<c:val><c:numLit><c:formatCode>#,##0.00</c:formatCode><c:ptCount val="{len(spec.values)}"/>{value_points}</c:numLit></c:val>
</c:ser><c:dLbls><c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="0"/><c:showSerName val="0"/></c:dLbls><c:gapWidth val="85"/><c:axId val="48650112"/><c:axId val="48672768"/></c:barChart>
<c:catAx><c:axId val="48650112"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="b"/><c:numFmt formatCode="General" sourceLinked="1"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr><a:ln><a:solidFill><a:srgbClr val="CBD5E1"/></a:solidFill></a:ln></c:spPr><c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="800"/></a:pPr><a:endParaRPr lang="ru-RU"/></a:p></c:txPr><c:crossAx val="48672768"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/></c:catAx>
<c:valAx><c:axId val="48672768"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="l"/><c:majorGridlines><c:spPr><a:ln><a:solidFill><a:srgbClr val="E2E8F0"/></a:solidFill></a:ln></c:spPr></c:majorGridlines><c:numFmt formatCode="# ##0 &quot;₽&quot;" sourceLinked="0"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr><a:ln><a:solidFill><a:srgbClr val="CBD5E1"/></a:solidFill></a:ln></c:spPr><c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="800"/></a:pPr><a:endParaRPr lang="ru-RU"/></a:p></c:txPr><c:crossAx val="48650112"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>
</c:plotArea><c:plotVisOnly val="0"/><c:dispBlanksAs val="gap"/><c:showDLblsOverMax val="0"/></c:chart>
<c:printSettings><c:headerFooter/><c:pageMargins b="0.75" l="0.7" r="0.7" t="0.75" header="0.3" footer="0.3"/><c:pageSetup/></c:printSettings>
</c:chartSpace>'''
    return xml.encode("utf-8")


def drawing_xml(spec: ChartSpec) -> bytes:
    xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<xdr:twoCellAnchor editAs="oneCell"><xdr:from><xdr:col>{spec.from_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{spec.from_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>{spec.to_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{spec.to_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="2" name="Финансовая структура"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart r:id="rId1"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor></xdr:wsDr>'''
    return xml.encode("utf-8")


def drawing_relationships_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>'
        '</Relationships>'
    ).encode("utf-8")


def worksheet_drawing_relationships_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>'
        '</Relationships>'
    ).encode("utf-8")
