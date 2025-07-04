"""
Queue Manager for Bioreactor Hub
Handles experiment queuing with persistence and user management.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import threading

logger = logging.getLogger(__name__)

class ExperimentStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

@dataclass
class Experiment:
    experiment_id: str
    user_session_id: str
    script_content: str
    status: ExperimentStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    priority: int = 0  # For future priority system
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Experiment':
        """Create from dictionary for JSON deserialization"""
        data['status'] = ExperimentStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('started_at'):
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if data.get('completed_at'):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        return cls(**data)

class QueueManager:
    """Manages experiment queue with persistence"""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.queue_file = self.data_dir / "experiment_queue.json"
        self.experiments: Dict[str, Experiment] = {}
        self.queue_order: List[str] = []
        self.lock = threading.Lock()
        self.max_experiments_per_user = 5
        
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing queue
        self._load_queue()
    
    def _load_queue(self):
        """Load queue from JSON file"""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                
                # Load experiments
                self.experiments = {
                    exp_id: Experiment.from_dict(exp_data)
                    for exp_id, exp_data in data.get('experiments', {}).items()
                }
                
                # Load queue order
                self.queue_order = data.get('queue_order', [])
                
                # Clean up completed experiments older than 24 hours
                self._cleanup_old_experiments()
                
                logger.info(f"Loaded {len(self.experiments)} experiments from queue file")
            else:
                logger.info("No existing queue file found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load queue: {e}")
            self.experiments = {}
            self.queue_order = []
    
    def _save_queue(self):
        """Save queue to JSON file"""
        try:
            with self.lock:
                data = {
                    'experiments': {
                        exp_id: exp.to_dict()
                        for exp_id, exp in self.experiments.items()
                    },
                    'queue_order': self.queue_order
                }
                
                with open(self.queue_file, 'w') as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")
    
    def _cleanup_old_experiments(self):
        """Remove completed experiments older than 24 hours"""
        cutoff_time = datetime.now() - timedelta(hours=24)
        to_remove = []
        
        for exp_id, experiment in self.experiments.items():
            if (experiment.status in [ExperimentStatus.COMPLETED, ExperimentStatus.FAILED, ExperimentStatus.CANCELLED] and
                experiment.completed_at and experiment.completed_at < cutoff_time):
                to_remove.append(exp_id)
        
        for exp_id in to_remove:
            del self.experiments[exp_id]
            if exp_id in self.queue_order:
                self.queue_order.remove(exp_id)
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old experiments")
            self._save_queue()
    
    def add_experiment(self, user_session_id: str, script_content: str) -> Dict[str, Any]:
        """Add experiment to queue"""
        with self.lock:
            # Check user limit
            user_experiments = [
                exp for exp in self.experiments.values()
                if exp.user_session_id == user_session_id and
                exp.status in [ExperimentStatus.QUEUED, ExperimentStatus.RUNNING]
            ]
            
            if len(user_experiments) >= self.max_experiments_per_user:
                return {
                    "success": False,
                    "error": f"Maximum {self.max_experiments_per_user} experiments allowed per user"
                }
            
            # Create new experiment
            experiment_id = str(uuid.uuid4())
            experiment = Experiment(
                experiment_id=experiment_id,
                user_session_id=user_session_id,
                script_content=script_content,
                status=ExperimentStatus.QUEUED,
                created_at=datetime.now()
            )
            
            # Add to queue
            self.experiments[experiment_id] = experiment
            self.queue_order.append(experiment_id)
            
            # Save to file
            self._save_queue()
            
            logger.info(f"Added experiment {experiment_id} to queue for user {user_session_id}")
            
            return {
                "success": True,
                "experiment_id": experiment_id,
                "queue_position": len(self.queue_order)
            }
    
    def get_next_experiment(self) -> Optional[Experiment]:
        """Get next experiment from queue"""
        with self.lock:
            for exp_id in self.queue_order:
                experiment = self.experiments[exp_id]
                if experiment.status == ExperimentStatus.QUEUED:
                    return experiment
            return None
    
    def start_experiment(self, experiment_id: str) -> bool:
        """Mark experiment as running"""
        with self.lock:
            if experiment_id in self.experiments:
                experiment = self.experiments[experiment_id]
                if experiment.status == ExperimentStatus.QUEUED:
                    experiment.status = ExperimentStatus.RUNNING
                    experiment.started_at = datetime.now()
                    self._save_queue()
                    logger.info(f"Started experiment {experiment_id}")
                    return True
            return False
    
    def complete_experiment(self, experiment_id: str, exit_code: int, error_message: Optional[str] = None):
        """Mark experiment as completed"""
        with self.lock:
            if experiment_id in self.experiments:
                experiment = self.experiments[experiment_id]
                experiment.status = ExperimentStatus.COMPLETED if exit_code == 0 else ExperimentStatus.FAILED
                experiment.completed_at = datetime.now()
                experiment.exit_code = exit_code
                experiment.error_message = error_message
                self._save_queue()
                logger.info(f"Completed experiment {experiment_id} with exit code {exit_code}")
    
    def cancel_experiment(self, experiment_id: str) -> bool:
        """Cancel experiment"""
        with self.lock:
            if experiment_id in self.experiments:
                experiment = self.experiments[experiment_id]
                if experiment.status == ExperimentStatus.QUEUED:
                    experiment.status = ExperimentStatus.CANCELLED
                    experiment.completed_at = datetime.now()
                    self._save_queue()
                    logger.info(f"Cancelled experiment {experiment_id}")
                    return True
            return False
    
    def pause_experiment(self, experiment_id: str) -> bool:
        """Pause experiment (only works for queued experiments)"""
        with self.lock:
            if experiment_id in self.experiments:
                experiment = self.experiments[experiment_id]
                if experiment.status == ExperimentStatus.QUEUED:
                    experiment.status = ExperimentStatus.PAUSED
                    self._save_queue()
                    logger.info(f"Paused experiment {experiment_id}")
                    return True
            return False
    
    def resume_experiment(self, experiment_id: str) -> bool:
        """Resume paused experiment"""
        with self.lock:
            if experiment_id in self.experiments:
                experiment = self.experiments[experiment_id]
                if experiment.status == ExperimentStatus.PAUSED:
                    experiment.status = ExperimentStatus.QUEUED
                    self._save_queue()
                    logger.info(f"Resumed experiment {experiment_id}")
                    return True
            return False
    
    def reorder_experiment(self, experiment_id: str, new_position: int) -> bool:
        """Reorder experiment in queue"""
        with self.lock:
            if experiment_id in self.queue_order:
                # Remove from current position
                self.queue_order.remove(experiment_id)
                
                # Insert at new position
                new_position = max(0, min(new_position, len(self.queue_order)))
                self.queue_order.insert(new_position, experiment_id)
                
                self._save_queue()
                logger.info(f"Reordered experiment {experiment_id} to position {new_position}")
                return True
            return False
    
    def get_experiment_status(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get experiment status"""
        if experiment_id in self.experiments:
            experiment = self.experiments[experiment_id]
            queue_position = None
            
            if experiment.status == ExperimentStatus.QUEUED:
                try:
                    queue_position = self.queue_order.index(experiment_id) + 1
                except ValueError:
                    pass
            
            return {
                "experiment_id": experiment.experiment_id,
                "status": experiment.status.value,
                "queue_position": queue_position,
                "created_at": experiment.created_at.isoformat(),
                "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
                "completed_at": experiment.completed_at.isoformat() if experiment.completed_at else None,
                "exit_code": experiment.exit_code,
                "error_message": experiment.error_message
            }
        return None
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get overall queue status"""
        with self.lock:
            queued_count = len([exp for exp in self.experiments.values() if exp.status == ExperimentStatus.QUEUED])
            running_count = len([exp for exp in self.experiments.values() if exp.status == ExperimentStatus.RUNNING])
            paused_count = len([exp for exp in self.experiments.values() if exp.status == ExperimentStatus.PAUSED])
            
            # Calculate estimated wait time (rough estimate: 10 minutes per experiment)
            estimated_wait_minutes = queued_count * 10
            
            return {
                "total_queued": queued_count,
                "total_running": running_count,
                "total_paused": paused_count,
                "estimated_wait_minutes": estimated_wait_minutes,
                "queue": [
                    {
                        "experiment_id": exp_id,
                        "user_session_id": self.experiments[exp_id].user_session_id,
                        "status": self.experiments[exp_id].status.value,
                        "created_at": self.experiments[exp_id].created_at.isoformat()
                    }
                    for exp_id in self.queue_order
                    if exp_id in self.experiments
                ]
            }
    
    def get_user_experiments(self, user_session_id: str) -> List[Dict[str, Any]]:
        """Get all experiments for a user"""
        user_experiments = []
        
        for experiment in self.experiments.values():
            if experiment.user_session_id == user_session_id:
                queue_position = None
                if experiment.status == ExperimentStatus.QUEUED:
                    try:
                        queue_position = self.queue_order.index(experiment.experiment_id) + 1
                    except ValueError:
                        pass
                
                user_experiments.append({
                    "experiment_id": experiment.experiment_id,
                    "status": experiment.status.value,
                    "queue_position": queue_position,
                    "created_at": experiment.created_at.isoformat(),
                    "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
                    "completed_at": experiment.completed_at.isoformat() if experiment.completed_at else None,
                    "exit_code": experiment.exit_code,
                    "error_message": experiment.error_message
                })
        
        return sorted(user_experiments, key=lambda x: x["created_at"], reverse=True) 
