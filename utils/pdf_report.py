import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from xml.sax.saxutils import escape

def generate_report(
    report_id: str,
    pipeline: dict,
    sensor_readings: dict,
    observations_df,
    anomaly_info: dict,
    recommendations: list,
    output_path: str = None,
):
    """
    Generates MethaTrace Inspection PDF report and returns bytes.
    
    Parameters:
        report_id (str): Unique report identifier.
        pipeline (dict): Pipeline metadata keys:
            'pipeline_id', 'start_coords', 'end_coords', 'installation_year',
            'material', 'status'.
        sensor_readings (dict): Sensor data with keys:
            'pressure_bar', 'flow_rate_m3h', 'sensor_status' (simulated).
        observations_df (pd.DataFrame): Observation rows relevant to this pipeline.
        anomaly_info (dict): {
            'threshold_anomaly_count': int,
            'ml_anomaly_count': int,
            'source_label_counts': dict (source_label -> count)
        }
        recommendations (list): List of recommendation strings.
        output_path (str): Optional path to save PDF file. If None, returns bytes.
        
    Returns:
        bytes: PDF file content as bytes if output_path is None.
    """

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    heading_style = styles['Heading1']
    heading2_style = styles['Heading2']
    heading3_style = styles['Heading3']
    italic_style = ParagraphStyle('italic', parent=normal_style, fontName='Helvetica-Oblique', fontSize=9)
    small_style = ParagraphStyle('small', parent=normal_style, fontSize=9)

    elements = []

    # Title
    elements.append(Paragraph("MethaTrace", heading_style))
    elements.append(Paragraph("Inspection Report", heading2_style))
    elements.append(Spacer(1, 12))

    # Report ID and Timestamp
    gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"<b>Report ID:</b> {escape(str(report_id))}", normal_style))
    elements.append(Paragraph(f"<b>Report Generated:</b> {gen_time}", normal_style))
    elements.append(Spacer(1, 12))

    # Pipeline Information
    elements.append(Paragraph("Pipeline Details", heading3_style))

    def fmt_coord(coord):
        if (
            coord is None
            or not hasattr(coord, '__iter__')
            or len(coord) != 2
            or coord[0] is None
            or coord[1] is None
        ):
            return "N/A"
        try:
            lat, lon = float(coord[0]), float(coord[1])
            return f"{lat:.6f}, {lon:.6f}"
        except Exception:
            return "N/A"

    pipeline_table_data = [
        ["Pipeline ID:", escape(str(pipeline.get('pipeline_id', "N/A")))],
        ["Location (Start, End):",
         f"{fmt_coord(pipeline.get('start_coords', None))} → {fmt_coord(pipeline.get('end_coords', None))}"],
        ["Installation Year:", escape(str(pipeline.get('installation_year', "N/A")))],
        ["Material:", escape(str(pipeline.get('material', "N/A")))],
        ["Status:", escape(str(pipeline.get('status', "N/A")))],
    ]

    table = Table(pipeline_table_data, hAlign='LEFT', colWidths=[4*cm, 11*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))

    # Risk Summary
    elements.append(Paragraph("Anomaly Summary", heading3_style))

    # Safely convert counts to int and back to str
    threshold_count = int(anomaly_info.get('threshold_anomaly_count', 0))
    ml_count = int(anomaly_info.get('ml_anomaly_count', 0))
    anomaly_text = (
        f"Threshold-based anomalies detected: {threshold_count}<br/>"
        f"ML-detected anomalies detected: {ml_count}"
    )
    elements.append(Paragraph(anomaly_text, normal_style))
    elements.append(Spacer(1, 12))

    # Contributing Factors
    elements.append(Paragraph("Contributing Source Labels Behind Anomalies:", heading3_style))
    source_label_counts = anomaly_info.get('source_label_counts', {})
    if source_label_counts and isinstance(source_label_counts, dict):
        factors_data = [["Source Label", "Count"]]
        for label, count in sorted(source_label_counts.items(), key=lambda x: x[1], reverse=True):
            factors_data.append([escape(str(label)), str(int(count))])
        factors_table = Table(factors_data, hAlign="LEFT", colWidths=[8*cm, 4*cm])
        factors_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ]))
        elements.append(factors_table)
    else:
        elements.append(Paragraph("No contributing factors available.", normal_style))
    elements.append(Spacer(1, 12))

    # Sensor Readings (show only if dict and keys exist)
    elements.append(Paragraph("Sensor Readings", heading3_style))
    if sensor_readings and isinstance(sensor_readings, dict):
        pressure = sensor_readings.get('pressure_bar', 'N/A')
        flow = sensor_readings.get('flow_rate_m3h', 'N/A')
        status = sensor_readings.get('sensor_status', 'N/A')
        # Escape status string
        status_safe = escape(str(status))
        sensor_text = (
            f"Pressure (Bar): {pressure}<br/>"
            f"Flow Rate (m³/h): {flow}<br/>"
            f"Sensor Status: {status_safe} <i>(Simulated Data)</i>"
        )
        elements.append(Paragraph(sensor_text, normal_style))
    else:
        elements.append(Paragraph("No sensor readings available.", normal_style))
    elements.append(Spacer(1, 12))

    # Observation Details Table
    elements.append(Paragraph("Observation Details (Recent Methane Concentrations)", heading3_style))
    obs_rows = [["Timestamp", "Methane Concentration (ppm)", "Threshold Anomaly", "ML Anomaly"]]

    if observations_df is not None and not observations_df.empty:
        for _, row in observations_df.iterrows():
            ts = row.get('timestamp', 'N/A')
            if hasattr(ts, 'strftime'):
                ts = ts.strftime('%Y-%m-%d %H:%M:%S')
            methane_ppm = row.get('methane_concentration_ppm', 'N/A')

            # Boolean flags correct handling
            threshold_flag = row.get('is_anomaly', False)
            if not isinstance(threshold_flag, bool):
                threshold_flag = bool(threshold_flag)
            threshold_flag_str = "Yes" if threshold_flag else "No"

            ml_flag = row.get('is_ml_anomaly', False)
            if not isinstance(ml_flag, bool):
                ml_flag = bool(ml_flag)
            ml_flag_str = "Yes" if ml_flag else "No"

            # Escape strings
            ts_safe = escape(str(ts))
            methane_safe = escape(str(methane_ppm))

            obs_rows.append([ts_safe, methane_safe, threshold_flag_str, ml_flag_str])
    else:
        obs_rows.append(["No observations available", "", "", ""])

    obs_table = Table(obs_rows, colWidths=[5*cm, 5*cm, 3*cm, 3*cm], repeatRows=1)
    obs_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(obs_table)
    elements.append(Spacer(1, 12))

    # Recommendations
    elements.append(Paragraph("Recommendations", heading3_style))
    if recommendations and isinstance(recommendations, (list, tuple)) and len(recommendations) > 0:
        for rec in recommendations:
            text = escape(str(rec))
            elements.append(Paragraph(f"- {text}", normal_style))
    else:
        elements.append(Paragraph("No recommendations provided.", normal_style))
    elements.append(Spacer(1, 12))

    # Data Provenance and Disclaimer 
    elements.append(PageBreak())
    elements.append(Paragraph("Data Provenance & Disclaimer", heading2_style))
    disclaimer_text = (
        "This report is generated using <b>SYNTHETIC DEMONSTRATION DATA – NOT REAL FIELD MEASUREMENTS</b>. "
        "The methane concentration values, sensor readings, and anomaly detections are simulated "
        "for demonstration and educational purposes only and do not represent actual field data."
    )
    elements.append(Paragraph(disclaimer_text, normal_style))
    elements.append(Spacer(1, 6))
    provenance_text = (
        "Pipeline and observation data are generated synthetically using physical simulation and "
        "randomized environmental parameters as described in the MethaTrace project documentation."
    )
    elements.append(Paragraph(provenance_text, normal_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Report generated on {gen_time}", italic_style))
    elements.append(Spacer(1, 12))

    # Page number canvas callback
    def add_page_number(c, doc):
        page_num = c.getPageNumber()
        text = f"Page {page_num}"
        c.setFont("Helvetica", 9)
        c.drawRightString(A4[0] - 2*cm, 1.5*cm, text)

    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)

    if output_path:
        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())

    return buffer.getvalue()
