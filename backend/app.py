#!/usr/bin/env python3
"""
Flask backend for Cast & Crew Excel Timecard Processing
"""

from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import os
import json
from pathlib import Path
from timecard_pipeline import TimecardPipeline
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Flask to serve React build files
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# Initialize pipeline
pipeline = TimecardPipeline()


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Upload and process Excel file"""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith((".xlsx", ".xls", ".xlsm")):
        return (
            jsonify({"error": "Invalid file type. Please upload Excel files only."}),
            400,
        )

    try:
        # Save uploaded file
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)

        file_path = upload_dir / file.filename
        file.save(str(file_path))

        # Process the file through 3-step pipeline
        result = pipeline.process(str(file_path))

        # Clean up uploaded file
        os.remove(file_path)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error processing file: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/process-sample/<filename>")
def process_sample(filename):
    """Process a sample Excel file"""
    try:
        # Try multiple possible paths
        possible_paths = [
            Path("data") / filename,
            Path("sample") / filename,
            Path("../data") / filename,
            Path("../sample") / filename,
        ]

        sample_path = None
        for path in possible_paths:
            if path.exists():
                sample_path = path
                break

        if not sample_path:
            return (
                jsonify({"error": f"Sample file {filename} not found in any location"}),
                404,
            )

        logger.info(f"Processing sample file: {sample_path}")
        result = pipeline.process(str(sample_path))

        # Add debug info
        result["debug_info"] = {
            "file_path": str(sample_path),
            "file_exists": sample_path.exists(),
            "file_size": sample_path.stat().st_size if sample_path.exists() else 0,
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error processing sample {filename}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/samples")
def list_samples():
    """List available sample files"""
    try:
        samples = []

        # Check multiple directories
        sample_dirs = [Path("data"), Path("sample"), Path("../data"), Path("../sample")]

        for sample_dir in sample_dirs:
            if sample_dir.exists():
                samples.extend(
                    [
                        f.name
                        for f in sample_dir.glob("*.xlsx")
                        if not f.name.startswith("~$")
                    ]
                )
                samples.extend(
                    [
                        f.name
                        for f in sample_dir.glob("*.xlsm")
                        if not f.name.startswith("~$")
                    ]
                )

        # Remove duplicates
        samples = list(set(samples))
        return jsonify(samples)

    except Exception as e:
        logger.error(f"Error listing samples: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/review-queue")
def get_review_queue():
    """Get pending human review items"""
    try:
        queue = pipeline.get_review_queue()
        return jsonify(
            {
                "pending_reviews": queue,
                "total_count": len(queue),
                "high_priority": len(
                    [item for item in queue if item["priority"] == "high"]
                ),
                "medium_priority": len(
                    [item for item in queue if item["priority"] == "medium"]
                ),
                "low_priority": len(
                    [item for item in queue if item["priority"] == "low"]
                ),
            }
        )
    except Exception as e:
        logger.error(f"Error getting review queue: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/compliance-stats")
def get_compliance_stats():
    """Get compliance statistics"""
    try:
        # This would typically come from a database
        # For now, return mock stats based on the compliance rules
        compliance = pipeline.compliance

        return jsonify(
            {
                "federal_minimum_wage": compliance.federal_minimum_wage,
                "overtime_threshold": compliance.overtime_threshold,
                "max_weekly_hours": compliance.max_weekly_hours,
                "salary_exempt_threshold": compliance.salary_exempt_threshold,
                "overtime_multiplier": compliance.overtime_multiplier,
                "review_queue_size": len(pipeline.review_queue),
                "compliance_rules": {
                    "minimum_wage_enforcement": True,
                    "overtime_calculation": True,
                    "excessive_hours_flagging": True,
                    "salary_exempt_validation": True,
                    "human_review_triggers": [
                        "Hours > 60 per week",
                        "Rate below federal minimum",
                        "Salary-exempt working excessive hours",
                    ],
                },
            }
        )
    except Exception as e:
        logger.error(f"Error getting compliance stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "timecard-processor"})


# Serve React App
@app.route("/")
def serve_react_app():
    """Serve the React app"""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def serve_static_files(path):
    """Serve static files or fallback to React app"""
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    # Use different ports for development vs production
    if os.environ.get("FLASK_ENV") == "production":
        port = int(os.environ.get("PORT", 8080))
    else:
        port = 9000  # Development port

    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)
