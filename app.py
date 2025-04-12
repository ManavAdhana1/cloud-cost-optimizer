from flask import Flask, render_template, request, send_from_directory
import json
import os
from collections import defaultdict
from datetime import datetime
import matplotlib.pyplot as plt
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['CHART_FOLDER'] = 'static/charts'

# Create directories on startup
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CHART_FOLDER'], exist_ok=True)

OPTIMIZATION_RULES = {
    'EC2': {
        'condition': lambda s: s['cost'] > 90 or (s['usage_hours'] > 500 and not s.get('is_reserved')),
        'suggestion': "Switch to Reserved Instances for 1-year or 3-year commitment or use Spot Instances for non-critical workloads"
    },
    'S3': {
        'condition': lambda s: s['cost'] > 50 or (s['data_size_gb'] > 500 and not s.get('tiering_enabled')),
        'suggestion': "Implement Intelligent Tiering, enable lifecycle rules, and archive infrequently accessed data to Glacier"
    },
    'RDS': {
        'condition': lambda s: s['cost'] > 25 or (s['cpu_utilization'] < 20 and s.get('instance_type', '').startswith('db.m')),
        'suggestion': "Switch to Aurora Serverless or downsize your instance type if underutilized"
    },
    'Lambda': {
        'condition': lambda s: s['cost'] > 15 or (s['avg_duration_ms'] > 2000 and s['memory_mb'] > 1024),
        'suggestion': "Review function logic to reduce execution time, right-size memory, and consider asynchronous invocation patterns"
    },
    'CloudFront': {
        'condition': lambda s: s['cost'] > 30 or s.get('cache_hit_ratio', 100) < 80,
        'suggestion': "Optimize cache behaviors and TTL settings to increase cache hit ratio and reduce origin fetches"
    },
    'EBS': {
        'condition': lambda s: s['cost'] > 20 or (s.get('snapshot_count', 0) > 50 and not s.get('snapshot_cleanup_enabled')),
        'suggestion': "Use gp3 volumes for better performance at lower cost, and implement automated snapshot cleanup"
    },
    'ECS': {
        'condition': lambda s: s['cost'] > 40 or (s.get('avg_cpu_utilization', 100) < 30),
        'suggestion': "Right-size your ECS tasks, enable autoscaling, and consider moving to Fargate for smaller workloads"
    }
}


def analyze_cost(data):
    if not data['months']:
        raise ValueError("No monthly data found in the report")

    # Validate cost values
    for month in data['months']:
        for service in month['services']:
            if not isinstance(service['cost'], (int, float)):
                raise ValueError(f"Invalid cost format for {service['name']} in {month['month']}")

    # Sort months chronologically
    try:
        data['months'].sort(key=lambda x: (
            datetime.strptime(x['month'], '%B %Y') if ' ' in x['month'] 
            else datetime.strptime(x['month'] + ' 2024', '%B %Y')
        ))
    except ValueError as e:
        raise ValueError(f"Invalid month format: {str(e)}")

    months_order = [m['month'] for m in data['months']]
    service_costs = defaultdict(lambda: defaultdict(float))

    # Collect service costs
    for month_data in data['months']:
        for service in month_data['services']:
            service_costs[service['name']][month_data['month']] += service['cost']

    # Build service history
    service_history = defaultdict(list)
    for service, costs in service_costs.items():
        service_history[service] = [{
            'month': month,
            'cost': costs.get(month, 0.0)
        } for month in months_order]

    # Process latest month
    latest_month = data['months'][-1].copy()
    if 'total_cost' not in latest_month:
        latest_month['total_cost'] = sum(s['cost'] for s in latest_month['services'])

    # Generate recommendations
    recommendations = []
    for service in latest_month['services']:
        if service['name'] in OPTIMIZATION_RULES:
            rule = OPTIMIZATION_RULES[service['name']]
            if rule['condition'](service):
                recommendations.append(rule['suggestion'])

    # Calculate all-time total
    total_all_months = sum(
        month['total_cost'] if 'total_cost' in month else 
        sum(service['cost'] for service in month['services'])
        for month in data['months']
    )

    return {
        'recommendations': list(set(recommendations)),
        'service_history': service_history,
        'latest_month': latest_month,
        'all_months': [{'month': m} for m in months_order],
        'total_all_months': total_all_months
    }

def generate_charts(service_history, all_months, chart_folder, months_data):
    plt.style.use('ggplot')
    months_order = [m['month'] for m in all_months]
    
    # Service Cost Distribution
    plt.figure(figsize=(14, 7), facecolor='#f8fafc')
    ax = plt.gca()
    ax.set_facecolor('#ffffff')
    
    colors = ['#4C72B0', '#55A868', '#8172B2', '#CCB974']
    for idx, (service, history) in enumerate(service_history.items()):
        costs = [h['cost'] for h in history]
        plt.plot(months_order, costs, 
                marker='o', 
                linewidth=2.5,
                markersize=8,
                color=colors[idx % len(colors)],
                label=service)
    
    plt.title('Service Cost Trends', pad=20, fontsize=16, fontweight='bold')
    plt.xlabel('Month', labelpad=15)
    plt.ylabel('Cost ($)', labelpad=15)
    plt.xticks(rotation=45, ha='right')
    plt.legend(frameon=True, shadow=True, loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(chart_folder, 'service_cost_distribution.png'), dpi=120)
    plt.close()

    # Total Cost Trend
    plt.figure(figsize=(14, 7), facecolor='#f8fafc')
    ax = plt.gca()
    ax.set_facecolor('#ffffff')
    
    total_costs = [next((m['total_cost'] for m in months_data if m['month'] == month), 0) 
                  for month in months_order]
    
    plt.plot(months_order, total_costs, 
            marker='o', 
            color='#2ecc71',
            linewidth=2.5,
            markersize=8)
    
    plt.title('Total Cost Progression', pad=20, fontsize=16, fontweight='bold')
    plt.xlabel('Month', labelpad=15)
    plt.ylabel('Total Cost ($)', labelpad=15)
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(chart_folder, 'cost_trends.png'), dpi=120)
    plt.close()

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html', error='No file selected')

        file = request.files['file']
        if not file or file.filename == '':
            return render_template('index.html', error='No file selected')

        if file.filename.endswith('.json'):
            try:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                with open(filepath) as f:
                    data = json.load(f)

                analysis = analyze_cost(data)
                generate_charts(
                    analysis['service_history'],
                    analysis['all_months'],
                    app.config['CHART_FOLDER'],
                    data['months']
                )

                return render_template('results.html',
                    recommendations=analysis['recommendations'],
                    latest_month=analysis['latest_month'],
                    total_all_months=analysis['total_all_months'],
                    uploaded_file=filename)

            except Exception as e:
                return render_template('index.html', error=f'Error: {str(e)}')

    return render_template('index.html')

@app.route('/charts/<filename>')
def charts(filename):
    return send_from_directory(app.config['CHART_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)