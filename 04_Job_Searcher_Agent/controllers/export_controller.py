import os
import csv
from datetime import datetime
from typing import List
from models.job import Job
from config.settings import settings
from utils.helpers import sanitize_filename


class ExportController:
    """Handles CSV export of job listings."""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def export_to_csv(self, jobs: List[Job], filename: str = None) -> str:
        if not jobs:
            raise ValueError("No jobs to export.")

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jobs_{ts}.csv"

        filename = sanitize_filename(filename)
        if not filename.endswith(".csv"):
            filename += ".csv"

        filepath = os.path.join(self.output_dir, filename)
        fieldnames = list(jobs[0].to_dict().keys())

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for job in jobs:
                writer.writerow(job.to_dict())

        return filepath

    def update_applied_status(self, jobs: List[Job], filepath: str):
        """Re-export CSV with updated applied status."""
        self.export_to_csv(jobs, os.path.basename(filepath))