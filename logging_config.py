"""
Logging configuration for the paper2xmind application
"""
import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logging(log_level=logging.INFO, log_file=None):
    """
    Setup logging configuration
    
    Args:
        log_level: Logging level (default: INFO)
        log_file: Log file path (optional)
    """
    # Create logs directory if it doesn't exist
    logs_dir = Path("./logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file is None:
        log_file = logs_dir / f"paper2xmind_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name):
    """
    Get a logger with the specified name
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger
    """
    return logging.getLogger(name)


# Pre-configured loggers for different modules
app_logger = get_logger("paper2xmind.app")
analysis_logger = get_logger("paper2xmind.analysis")
pdf_logger = get_logger("paper2xmind.pdf")
xmind_logger = get_logger("paper2xmind.xmind")


if __name__ == "__main__":
    # Test the logging setup
    setup_logging()
    app_logger.info("Logging system initialized successfully")
    app_logger.debug("Debug message for testing")
    app_logger.warning("Warning message for testing")
    print("✅ Logging configuration test completed")