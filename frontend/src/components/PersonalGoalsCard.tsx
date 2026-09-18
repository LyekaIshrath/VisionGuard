import React, { useState } from "react";
import { PersonalGoal, GoalType } from "../types";

interface Props {
  goals: PersonalGoal[];
  onSaveGoal: (goalType: GoalType, target: number) => Promise<void>;
  onDeleteGoal: (goalId: string) => Promise<void>;
}

export const PersonalGoalsCard: React.FC<Props> = ({ goals, onSaveGoal, onDeleteGoal }) => {
  const [editingGoal, setEditingGoal] = useState<GoalType | null>(null);
  const [targetInput, setTargetInput] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const goalDefs: { type: GoalType; title: string; unit: string; defaultTarget: number; description: string }[] = [
    {
      type: "DAILY_MONITORING_MINUTES",
      title: "Daily Monitored Time",
      unit: "minutes",
      defaultTarget: 60,
      description: "Active time monitored by VisionGuard today",
    },
    {
      type: "GOOD_POSTURE_PERCENTAGE",
      title: "Good Posture Ratio",
      unit: "%",
      defaultTarget: 80,
      description: "Observation time spent with good posture alignment",
    },
    {
      type: "MAX_POSTURE_RISK_EVENTS_PER_HOUR",
      title: "Maximum Risk Rate",
      unit: "events/hr",
      defaultTarget: 5,
      description: "Ceiling for posture risk alerts per observation hour",
    },
  ];

  const handleStartEdit = (type: GoalType, currentTarget?: number, defaultTarget: number = 60) => {
    setEditingGoal(type);
    setTargetInput(currentTarget !== undefined ? currentTarget.toString() : defaultTarget.toString());
  };

  const handleSave = async (type: GoalType) => {
    const val = parseFloat(targetInput);
    if (isNaN(val) || val <= 0) return;
    try {
      setSaving(true);
      await onSaveGoal(type, val);
      setEditingGoal(null);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="goals-card-container">
      <div className="goals-header">
        <h3 className="section-title">Personal Wellness Goals</h3>
        <span className="goals-subtitle">Set healthy targets without aggressive or punitive streaks</span>
      </div>

      <div className="goals-grid">
        {goalDefs.map((def) => {
          const userGoal = goals.find((g) => g.goal_type === def.type);
          const isEditing = editingGoal === def.type;
          const target = userGoal ? userGoal.target_value : def.defaultTarget;
          const current = userGoal?.current_value !== undefined ? userGoal.current_value : null;
          const progress = userGoal?.progress_percentage !== undefined ? userGoal.progress_percentage : 0;
          const achieved = userGoal?.achieved ?? false;

          return (
            <div key={def.type} className={`goal-item-card ${achieved ? "achieved" : ""}`}>
              <div className="goal-card-top">
                <h4 className="goal-title">{def.title}</h4>
                {achieved && <span className="goal-achieved-pill">🎯 Achieved</span>}
              </div>
              <p className="goal-desc">{def.description}</p>

              {isEditing ? (
                <div className="goal-edit-row">
                  <input
                    type="number"
                    className="goal-input"
                    value={targetInput}
                    onChange={(e) => setTargetInput(e.target.value)}
                    step={def.type === "GOOD_POSTURE_PERCENTAGE" ? "1" : "5"}
                    min="1"
                    max={def.type === "GOOD_POSTURE_PERCENTAGE" ? "100" : "1000"}
                  />
                  <span className="goal-unit">{def.unit}</span>
                  <button
                    className="goal-btn-save"
                    disabled={saving}
                    onClick={() => handleSave(def.type)}
                  >
                    Save
                  </button>
                  <button className="goal-btn-cancel" onClick={() => setEditingGoal(null)}>
                    ✕
                  </button>
                </div>
              ) : (
                <div className="goal-status-row">
                  <div className="goal-values">
                    <span className="goal-current">
                      {current !== null ? `${current} ${def.unit}` : `-- ${def.unit}`}
                    </span>
                    <span className="goal-target">/ {target} {def.unit} target</span>
                  </div>
                  <div className="goal-btn-group">
                    <button
                      className="goal-btn-edit"
                      onClick={() => handleStartEdit(def.type, userGoal?.target_value, def.defaultTarget)}
                    >
                      Adjust
                    </button>
                    {userGoal?.id && (
                      <button
                        className="goal-btn-delete"
                        title="Reset goal to default"
                        onClick={() => onDeleteGoal(userGoal.id!)}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>
              )}

              <div className="goal-progress-bar-wrapper">
                <div
                  className={`goal-progress-bar ${achieved ? "completed" : ""}`}
                  style={{ width: `${Math.min(100, Math.max(0, progress || 0))}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
