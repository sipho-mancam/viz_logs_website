from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from .models import VizData
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from io import BytesIO
from datetime import datetime

def format_time_duration(seconds):
    if seconds is None:
        return "N/A"
    try:
        seconds = float(seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "00:00:00"
    

def combine_groups_on_viz_name(data:list[VizData])->list[VizData]:
    """Combine VizData entries by viz_name, summing time_on_air and time_on_camera"""
    result = {}
    for item in data:
        if item.sponsor_logo_name not in result:
            result[item.sponsor_logo_name] = {
                'group_id': item.group_id,
                'display_name': item.display_name,
                'sponsor_logo_name': item.sponsor_logo_name,
                'time_on_air': item.time_on_air or 0,
                'visiblity_map': item.visibility_map,
                'time_on_camera': item.time_on_camera or 0,
                'created_at': item.created_at
            }
        else:
            result[item.sponsor_logo_name]['time_on_air'] += item.time_on_air or 0
            result[item.sponsor_logo_name]['time_on_camera'] += item.time_on_camera or 0
            result[item.sponsor_logo_name]['group_id'] += " + " + item.group_id
            # Keep the latest created_at
            if item.created_at > result[item.sponsor_logo_name]['created_at']:
                result[item.sponsor_logo_name]['created_at'] = item.created_at
                
                result[item.sponsor_logo_name]['display_name'] = item.display_name
    
    combined_list = []
    for key in result:
        combined_item = VizData(
            group_id=result[key]['group_id'],
            display_name=result[key]['display_name'],
            sponsor_logo_name=result[key]['sponsor_logo_name'],
            time_on_air=result[key]['time_on_air'],
            time_on_camera=result[key]['time_on_camera'],
            created_at=result[key]['created_at']
        )
        combined_list.append(combined_item)

    return combined_list
    

def index(request):
    """Main view to display the data table"""
    # Get filter parameters
    search = request.GET.get('search', '')
    group_id_filter = request.GET.get('group_id', '')
    viz_name_filter = request.GET.get('viz_name', '')
    created_at_filter = request.GET.get('created_at', '')
    
    # Base query
    queryset = VizData.objects.all()
   
    
    # Apply filters
    if search:
        queryset = queryset.filter(
            Q(display_name__icontains=search) |
            Q(group_id__icontains=search) |
            Q(sponsor_logo_name__icontains=search)|
            Q(created_at__icontains=search),
        )
    
    if group_id_filter:
        queryset = queryset.filter(group_id=group_id_filter)
    
    if viz_name_filter:
        queryset = queryset.filter(sponsor_logo_name=viz_name_filter)
    
    if created_at_filter:
        # Accept either "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD" from the template,
        # parse the value and filter by the date portion only.
        date_val = None
        try:
            date_val = datetime.strptime(created_at_filter, '%Y-%m-%d %H:%M:%S').date()
        except ValueError:
            try:
                date_val = datetime.strptime(created_at_filter, '%Y-%m-%d').date()
            except ValueError:
                date_val = None

        if date_val:
            queryset = queryset.filter(created_at__date=date_val)
        else:
            # Fallback: try the original exact match if parsing failed
            print("Falling Back to default")
            queryset = queryset.filter(created_at=created_at_filter)
    
    # Get top 10 latest
    viz_data = queryset.order_by('group_id')
    
    # Get unique values for filters
    all_group_ids = VizData.objects.values_list('group_id', flat=True).distinct()
    all_viz_names = VizData.objects.values_list('sponsor_logo_name', flat=True).distinct()
    all_dates = [date["created_at"].date() for date in VizData.objects.values('created_at').distinct()]
    all_dates = set(all_dates)
    all_dates = list(all_dates)
    all_dates.sort(key=lambda x: x.toordinal(), reverse=True)
    
    
    context = {
        'viz_data': viz_data,
        'search': search,
        'group_id_filter': group_id_filter,
        'viz_name_filter': viz_name_filter,
        'created_at_filter': created_at_filter,
        'all_group_ids': all_group_ids,
        'all_viz_names': all_viz_names,
        'all_dates': all_dates,
    }
    
    return render(request, 'viz/index.html', context)

def get_histogram_data(request, pk):
    """API endpoint to get histogram data for a specific row"""
    try:
        viz_data = VizData.objects.get(pk=pk)
        histogram_data = viz_data.get_histogram_data()
        return JsonResponse({
            'success': True,
            'data': histogram_data,
            'display_name': viz_data.display_name or viz_data.group_id,
            'viz_name': viz_data.sponsor_logo_name
        })
    except VizData.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Data not found'}, status=404)

def export_pdf(request):
    """Export selected rows with their histograms to PDF"""
    # Get selected IDs from POST
    selected_ids = request.POST.getlist('selected_ids[]')
    
    if not selected_ids:
        return HttpResponse('No items selected', status=400)
    
    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                  topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()

     # Add letterhead to all pages
    def header(canvas, doc):
        # Draw the letterhead image
        canvas.saveState()
        img_path = 'static/image.png'  # Adjust path as needed
        print(f"left margin: {doc.leftMargin}, top margin: {doc.topMargin}, width: {doc.width}, height: {inch}")
        canvas.drawImage(img_path, doc.leftMargin-inch, doc.height - 0.5*inch, 
                        width=doc.width+2*inch, height=(1.8*inch), preserveAspectRatio=False)
        canvas.restoreState()

    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=10,
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=10,
    )

    bar_title = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=10,
        alignment=1,  # Center alignment
    )
    
    
    # Add title
    title = Paragraph(f"Virtual Logos Data Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", title_style)
    elements.append(Spacer(1, inch))
    elements.append(title)
    # elements.append(Spacer(1, 0.2*inch))
    
    # Get selected data
    viz_data_items = VizData.objects.filter(id__in=selected_ids).order_by('-created_at')

    currentVizItems = [item for item in viz_data_items]

    combined_items = combine_groups_on_viz_name(currentVizItems)
    
    for idx, item in enumerate(viz_data_items):
        if idx > 0:
            elements.append(PageBreak())
        
        # Add item heading
        item_title = f"{item.display_name or item.group_id} - {item.sponsor_logo_name or 'N/A'}"
        elements.append(Paragraph(item_title, heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Add details table
        details_data = [
            ['Camera ID:', item.group_id],
            ['Display Name:', item.display_name or 'N/A'],
            ['Sponsor Logo Name:', item.sponsor_logo_name or 'N/A'],
            ['Time on Air:', f"{format_time_duration(item.time_on_air)}"],
            ['Time on Camera:', f"{format_time_duration(item.time_on_camera)}"],
            ['Date Time:', item.created_at.strftime('%Y-%m-%d %H:%M:%S')],
        ]
        
        details_table = Table(details_data, colWidths=[2*inch, 4*inch])
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(details_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Add histogram
        histogram_data = item.get_histogram_data()
        if histogram_data['values']:
            # Create chart
            drawing = Drawing(400, 250)
            chart = VerticalBarChart()
            chart.x = 30
            chart.y = 30
            chart.height = 180
            chart.width = 350
            chart.data = [histogram_data['values']]
            chart.categoryAxis.categoryNames = histogram_data['labels']
            
            chart.categoryAxis.labels.angle = 45
            chart.categoryAxis.labels.fontSize = 8
            chart.categoryAxis.labels.dy = -15
            chart.categoryAxis.labels.fontName = 'Helvetica'
            
            chart.valueAxis.valueMin = 0
            chart.valueAxis.labels.fontSize = 8
            chart.valueAxis.labels.dx = -10
            chart.valueAxis.labels.fontName = 'Helvetica'
            chart.valueAxis.valueMax = max(histogram_data['values']) * 1.1 if histogram_data['values'] else 100
            chart.bars[0].fillColor = colors.HexColor('#3498db')
            chart.bars[0].strokeColor = colors.HexColor('#2980b9')
            chart.bars[0].strokeWidth = 0.5

            
            drawing.add(chart)
            elements.append(Paragraph("Percentage Visibility v. Time on Screen (%)", bar_title))
            elements.append(drawing)

    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(f"Combined Logo Time", title_style))
    elements.append(PageBreak())

    for idx, item in enumerate(combined_items):
        if idx % 3 == 0 and idx > 0:
            elements.append(PageBreak())
        
        # Add item heading
        item_title = f"{item.display_name or item.group_id} - {item.sponsor_logo_name or 'N/A'}"
        elements.append(Paragraph(item_title, heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Add details table
        details_data = [
            ['Camera ID:', item.group_id],
            ['Display Name:', item.display_name or 'N/A'],
            ['Sponsor Logo Name:', item.sponsor_logo_name or 'N/A'],
            ['Time on Air:', f"{format_time_duration(item.time_on_air)}"],
            ['Time on Camera:', f"{format_time_duration(item.time_on_camera)}"],
            ['Date Time:', item.created_at.strftime('%Y-%m-%d %H:%M:%S')],
        ]
        
        details_table = Table(details_data, colWidths=[2*inch, 4*inch])
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(details_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Add histogram
        histogram_data = item.get_histogram_data()
        if histogram_data['values']:
            # Create chart
            drawing = Drawing(400, 250)
            chart = VerticalBarChart()
            chart.x = 30
            chart.y = 30
            chart.height = 180
            chart.width = 350
            chart.data = [histogram_data['values']]
            chart.categoryAxis.categoryNames = histogram_data['labels']
            
            chart.categoryAxis.labels.angle = 45
            chart.categoryAxis.labels.fontSize = 8
            chart.categoryAxis.labels.dy = -15
            chart.categoryAxis.labels.fontName = 'Helvetica'
            
            chart.valueAxis.valueMin = 0
            chart.valueAxis.labels.fontSize = 8
            chart.valueAxis.labels.dx = -10
            chart.valueAxis.labels.fontName = 'Helvetica'
            chart.valueAxis.valueMax = max(histogram_data['values']) * 1.1 if histogram_data['values'] else 100
            chart.bars[0].fillColor = colors.HexColor('#3498db')
            chart.bars[0].strokeColor = colors.HexColor('#2980b9')
            chart.bars[0].strokeWidth = 0.5

            
            drawing.add(chart)
            elements.append(Paragraph("Percentage Visibility v. Time on Screen (%)", bar_title))
            elements.append(drawing)
    
    # Build PDF
    doc.build(elements, onFirstPage=header)
    buffer.seek(0)
    
    # Return PDF response
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="viz_data_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    return response
