"""
Email sender module for transcription pipeline.

Sends email notifications with processed lecture files as attachments.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends email notifications with file attachments."""
    
    def __init__(
        self,
        smtp_host: str = None,
        smtp_port: int = None,
        smtp_user: str = None,
        smtp_password: str = None,
        from_email: str = None
    ):
        """
        Initialize email sender.
        
        Args:
            smtp_host: SMTP server hostname (defaults to env SMTP_HOST)
            smtp_port: SMTP server port (defaults to env SMTP_PORT or 587)
            smtp_user: SMTP username (defaults to env SMTP_USER)
            smtp_password: SMTP password (defaults to env SMTP_PASSWORD)
            from_email: From email address (defaults to smtp_user)
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST")
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.from_email = from_email or self.smtp_user
        
        self.enabled = all([self.smtp_host, self.smtp_user, self.smtp_password])
        
        if self.enabled:
            logger.info(f"Email sender initialized: {self.smtp_user} via {self.smtp_host}")
        else:
            logger.debug("Email sender not configured (missing SMTP settings)")
    
    def send_lecture_complete(
        self,
        to_email: str,
        lecture_name: str,
        output_files: List[Path],
        profile_name: str = "social_work_lecture",
        user_name: str = "Kate",
        cc_email: Optional[str] = None
    ) -> bool:
        """
        Send email notification when lecture processing is complete.
        
        Args:
            to_email: Recipient email address
            lecture_name: Name of the lecture file
            output_files: List of output file paths to attach
            profile_name: Processing profile used
            user_name: Name of the recipient for personalization
            cc_email: Optional CC recipient (e.g., cohort member)
        
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email not sent: SMTP not configured")
            return False
        
        # Filter for Word documents only (smaller, more useful)
        docx_files = [f for f in output_files if f.suffix.lower() == ".docx"]
        
        if not docx_files:
            logger.warning("No .docx files to email")
            return False
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in docx_files)
        total_size_mb = total_size / (1024 * 1024)
        
        # Check size limit (most SMTP servers have 10-25MB limits)
        if total_size_mb > 20:
            logger.warning(f"Attachments too large ({total_size_mb:.1f}MB), sending only cheat sheet and analysis")
            # Prioritize smaller, more important files
            priority_files = [f for f in docx_files if "cheatsheet" in f.name.lower() or "analysis" in f.name.lower()]
            if not priority_files:
                priority_files = sorted(docx_files, key=lambda x: x.stat().st_size)[:2]
            docx_files = priority_files
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = to_email
            if cc_email:
                msg['Cc'] = cc_email
            msg['Subject'] = f"📚 Lecture Processed: {lecture_name}"
            
            # Email body
            body = f"""Hi {user_name},

Your lecture "{lecture_name}" has been processed and is ready!

Attached are {len(docx_files)} Word documents:

"""
            
            for i, f in enumerate(docx_files, 1):
                stage_name = f.stem.split('_')[-1].replace('-', ' ').title()
                size_kb = f.stat().st_size / 1024
                body += f"{i}. {stage_name} ({size_kb:.0f} KB)\n"
            
            body += """

These files are also available on your device via Syncthing in the "Processed Lectures" folder.

Happy studying!
- Your Transcription Pipeline 🤖
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach files
            for file_path in docx_files:
                try:
                    with open(file_path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                    
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{file_path.name}"'
                    )
                    msg.attach(part)
                    logger.debug(f"Attached: {file_path.name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to attach {file_path}: {e}")
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to_email} with {len(docx_files)} attachments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return self.enabled


def get_kate_email() -> Optional[str]:
    """Get Kate's email from environment."""
    return os.getenv("KATE_EMAIL") or os.getenv("NOTIFICATION_EMAIL")


def get_keira_email() -> Optional[str]:
    """Get Keira's email from environment."""
    return os.getenv("KEIRA_EMAIL") or os.getenv("NOTIFICATION_EMAIL")


def get_keira_cohort_email() -> Optional[str]:
    """Get Keira's cohort member email from environment (optional)."""
    return os.getenv("KEIRA_COHORT_EMAIL")
