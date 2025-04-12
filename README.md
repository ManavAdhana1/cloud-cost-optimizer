# ☁️ Cloud Cost Optimizer

An AI-powered billing analyzer that helps visualize cloud service expenses month-by-month.

## 💡 Features
- Upload your JSON billing report
- Get cost breakdowns
- Responsive and modern UI
- Dark theme with background image

## 📂 JSON Format Example
```json
{
  "months": [
    {
      "month": "April 2024",
      "services": [
        { "name": "EC2", "cost": 100.00 },
        { "name": "S3", "cost": 60.00 }
      ]
    }
  ]
}
