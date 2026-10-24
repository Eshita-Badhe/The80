"""Editable alarm semantics used by deterministic engines."""

from __future__ import annotations

ALARM_CODES = {
    "AFC901": {"severity": "MINOR", "role": "symptom", "meaning": "Gate communication error", "node_types": ["afc_gate"]},
    "AFC902": {"severity": "WARN", "role": "noise", "meaning": "Gate card reader timeout", "node_types": ["afc_gate"]},
    "AFC903": {"severity": "WARN", "role": "noise", "meaning": "Gate transaction timeout", "node_types": ["afc_gate"]},
    "ATP201": {"severity": "MINOR", "role": "symptom", "meaning": "ATP communication warning", "node_types": ["onboard_controller"]},
    "ATP205": {"severity": "MAJOR", "role": "symptom", "meaning": "ATP protection fault", "node_types": ["onboard_controller"]},
    "ECS002": {"severity": "MINOR", "role": "symptom", "meaning": "Ventilation fan VFD fault", "node_types": ["ecs"]},
    "HDW301": {"severity": "MINOR", "role": "symptom", "meaning": "Headway degradation warning", "node_types": ["zone_controller"]},
    "LVP601": {"severity": "MAJOR", "role": "root", "meaning": "LV panel trip", "node_types": ["lv_panel"]},
    "LVP602": {"severity": "MAJOR", "role": "root", "meaning": "LV panel voltage low", "node_types": ["lv_panel"]},
    "PSD401": {"severity": "WARN", "role": "noise", "meaning": "PSD obstruction", "node_types": ["platform_screen_door"]},
    "PSD402": {"severity": "MINOR", "role": "symptom", "meaning": "PSD controller communication error", "node_types": ["platform_screen_door"]},
    "PSD403": {"severity": "MAJOR", "role": "symptom", "meaning": "PSD controller fault", "node_types": ["platform_screen_door"]},
    "PSD404": {"severity": "MAJOR", "role": "symptom", "meaning": "PSD status unavailable", "node_types": ["platform_screen_door"]},
    "PSD405": {"severity": "MAJOR", "role": "symptom", "meaning": "PSD power fault", "node_types": ["platform_screen_door"]},
    "RTU001": {"severity": "MAJOR", "role": "symptom", "meaning": "Remote terminal unit alarm", "node_types": ["rtu"]},
    "TCM801": {"severity": "MAJOR", "role": "symptom", "meaning": "Door controller fault", "node_types": ["train_door"]},
    "TCM802": {"severity": "WARN", "role": "noise", "meaning": "Door obstruction detected", "node_types": ["train_door"]},
    "TCM803": {"severity": "MAJOR", "role": "symptom", "meaning": "Door controller communication error", "node_types": ["train_door"]},
    "TCM804": {"severity": "MINOR", "role": "symptom", "meaning": "Door close time exceeds limit", "node_types": ["train_door"]},
    "TCM810": {"severity": "MAJOR", "role": "symptom", "meaning": "Traction power interruption", "node_types": ["train_control_mgmt"]},
    "TCM811": {"severity": "MAJOR", "role": "symptom", "meaning": "Traction voltage low", "node_types": ["train_control_mgmt"]},
    "TCM812": {"severity": "WARN", "role": "noise", "meaning": "Train control heartbeat warning", "node_types": ["train_control_mgmt"]},
    "TSS702": {"severity": "MAJOR", "role": "root", "meaning": "Traction supply undervoltage", "node_types": ["traction_substation"]},
    "TSS703": {"severity": "WARN", "role": "precursor", "meaning": "Traction supply fluctuation", "node_types": ["traction_substation"]},
    "UPS501": {"severity": "MAJOR", "role": "symptom", "meaning": "UPS output failure", "node_types": ["ups"]},
    "UPS502": {"severity": "MAJOR", "role": "root", "meaning": "UPS battery failure", "node_types": ["ups"]},
    "UPS503": {"severity": "MAJOR", "role": "root", "meaning": "UPS bypass active", "node_types": ["ups"]},
    "UPS504": {"severity": "MINOR", "role": "precursor", "meaning": "UPS battery low", "node_types": ["ups"]},
    "UPS505": {"severity": "WARN", "role": "precursor", "meaning": "UPS battery temperature high", "node_types": ["ups"]},
    "ZC101": {"severity": "MAJOR", "role": "root", "meaning": "Zone controller communication fault", "node_types": ["zone_controller"]},
    "ZC102": {"severity": "MAJOR", "role": "root", "meaning": "Zone controller fault", "node_types": ["zone_controller"]},
    "ZC110": {"severity": "MAJOR", "role": "symptom", "meaning": "Zone controller downstream alarm", "node_types": ["zone_controller"]},
}

NOISE_CODES = {code for code, item in ALARM_CODES.items() if item["role"] == "noise"}

# Parent equipment patterns used by the deterministic root-cause scorer.
# Generic communication and obstruction alarms deliberately cast no vote.
FAILURE_PATTERNS = {
    "PSD405": {"node_types": ["ups", "lv_panel"]},
    "PSD404": {"node_types": ["zone_controller"]},
    "ATP201": {"node_types": ["zone_controller"]},
    "ATP205": {"node_types": ["zone_controller"]},
    "TCM810": {"node_types": ["traction_substation"]},
    "TCM811": {"node_types": ["traction_substation"]},
    "AFC901": {"node_types": ["lv_panel"]},
    "ESC002": {"node_types": ["lv_panel"]},
    "LFT001": {"node_types": ["lv_panel"]},
    "ECS001": {"node_types": ["lv_panel"]},
    "PSD402": {"node_types": []},
    "PSD403": {"node_types": []},
    "HDW301": {"node_types": []},
    "AFC902": {"node_types": []},
    "TCM802": {"node_types": []},
    "TCM803": {"node_types": []},
}

