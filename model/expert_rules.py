"""Expert-rule overlay to refine model predictions and produce better weekly schedules.

This is a core production module that provides:
- Exercise substitution based on equipment and injuries
- Safety constraints and volume caps
- Multi-week progression planning
- Smart exercise scheduling (push/pull/legs splits)
"""
from collections import defaultdict
import os
import json


def choose_split(days, goal):
    # Return a split type string based on days and goal
    if days <= 2:
        return "full_body"
    if days == 3:
        return "full_body_plus"
    if days == 4:
        return "upper_lower"
    if days == 5:
        return "push_pull_legs_plus"
    return "push_pull_legs"


def refine_predictions(preds, profile):
    # preds: {Exercise: {sets,reps,intensity}}
    # Apply simple expert rules:
    # - If goal is Strength => increase intensity by 1 and lower reps by 1-2
    # - If goal is Endurance => increase reps by 2 and lower intensity
    # - Cap weekly sets per muscle group to a safe limit (e.g., 20)
    goal = profile.get('Goal', '')
    days = profile.get('Days_per_Week', 4)

    # Adjustments
    for ex, v in preds.items():
        if goal == 'Strength':
            v['intensity'] = min(10, v['intensity'] + 1)
            v['reps'] = max(3, v['reps'] - 1)
        elif goal == 'Endurance':
            v['reps'] = v['reps'] + 2
            v['intensity'] = max(1, v['intensity'] - 1)
        elif goal == 'Muscle Gain':
            # small bump in sets for hypertrophy
            v['sets'] = int(round(v['sets'] * 1.05))

    # Safety caps: simple muscle group mapping and weekly set cap
    muscle_map = {
        'Bench': 'chest', 'OverheadPress': 'shoulders', 'Row': 'back',
        'Squat': 'legs', 'Deadlift': 'posterior_chain'
    }
    weekly_cap = {'legs': 25, 'chest': 20, 'back': 20, 'shoulders': 15, 'posterior_chain': 20}

    # Compute weekly total sets per muscle
    weekly_sets = defaultdict(int)
    for ex, v in preds.items():
        mg = muscle_map.get(ex, 'other')
        weekly_sets[mg] += v['sets']

    # If over cap, scale down proportionally
    for mg, total in list(weekly_sets.items()):
        cap = weekly_cap.get(mg, 30)
        if total > cap:
            scale = cap / total
            for ex, v in preds.items():
                if muscle_map.get(ex) == mg:
                    v['sets'] = max(1, int(round(v['sets'] * scale)))

    return preds


def schedule_exercises(preds, days):
    # Better scheduler: try push/pull/legs ordering when days >= 3
    exercises = list(preds.keys())
    schedule = {d: [] for d in range(1, days+1)}

    if days <= 2:
        # full body each session; distribute exercises evenly
        for i, ex in enumerate(exercises):
            day = (i % days) + 1
            schedule[day].append((ex, preds[ex]))
        return schedule

    # For 3+ days, create a simple split mapping
    push = {'Bench','OverheadPress'}
    pull = {'Row'}
    legs = {'Squat','Deadlift'}

    day_idx = 1
    # Assign push days
    for ex in exercises:
        if ex in push:
            schedule[day_idx].append((ex, preds[ex]))
    day_idx += 1
    # Assign pull days
    for ex in exercises:
        if ex in pull:
            schedule[day_idx].append((ex, preds[ex]))
    day_idx += 1
    # Assign legs days
    for ex in exercises:
        if ex in legs:
            schedule[day_idx].append((ex, preds[ex]))
    # Fill remaining days with remaining exercises or repeat
    rem = [ex for ex in exercises if ex not in push and ex not in pull and ex not in legs]
    for d in range(day_idx, days+1):
        for ex in rem:
            schedule[d].append((ex, preds[ex]))

    # If some days empty, move exercises round-robin
    all_assigned = sum(len(v) for v in schedule.values())
    if all_assigned == 0:
        for i, ex in enumerate(exercises):
            schedule[(i % days) + 1].append((ex, preds[ex]))

    return schedule


def generate_multiweek(preds, weeks=4, progression='linear'):
    # preds: base week predictions; return list of week-wise preds
    # progression: 'linear' increases intensity by +1 every 2 weeks and adds a set every 2 weeks
    weeks_out = []
    for w in range(weeks):
        week_preds = {}
        for ex, v in preds.items():
            sets = v['sets']
            reps = v['reps']
            intensity = v['intensity']
            # progression rules
            add_sets = (w // 2)  # add 1 set every 2 weeks
            add_int = (w // 2)   # add intensity step every 2 weeks
            week_preds[ex] = {
                'sets': max(1, sets + add_sets),
                'reps': reps,  # keep reps stable for simplicity
                'intensity': min(10, intensity + add_int)
            }
        weeks_out.append(week_preds)
    return weeks_out


def load_exercises_db(path=None):
    if path is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        path = os.path.join(project_root, 'data', 'exercises.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def substitute_exercises(preds, available_equipment, injuries=None, exercises_path=None):
    """Return preds with substitutions for unavailable equipment or injuries.

    preds: {Exercise: {sets,reps,intensity,...}}
    available_equipment: set or 'gym' to allow all
    injuries: list of body parts to avoid (strings)
    """
    if injuries is None:
        injuries = []
    injuries = [i.strip().lower() for i in injuries if i]

    db = load_exercises_db(exercises_path)

    # simple muscle mapping for our canonical exercises
    muscle_map = {
        'Bench': 'chest', 'OverheadPress': 'shoulders', 'Row': 'back',
        'Squat': 'legs', 'Deadlift': 'posterior_chain'
    }

    # Normalize available_equipment into a set of keywords or 'gym' flag
    if isinstance(available_equipment, str):
        eq = available_equipment.lower()
        if eq == 'gym':
            allowed_all = True
            allowed = set()
        elif eq == 'dumbbells':
            allowed_all = False
            allowed = {'dumbbell', 'body weight', 'band', 'kettlebell'}
        else:
            allowed_all = False
            allowed = {'body weight'}
    else:
        allowed_all = False
        allowed = set(available_equipment)

    new_preds = {}
    for ex, v in preds.items():
        mg = muscle_map.get(ex, None)
        # determine if ex is contraindicated by injury via body part match
        contraindicated = False
        # We will look for an exact name match in db to determine bodyParts/equipment
        found_exact = None
        for item in db:
            # basic name match: check if ex name in item name (case-insensitive)
            if ex.lower() in item.get('name','').lower():
                found_exact = item
                break
        if found_exact:
            bodyparts = [b.lower() for b in found_exact.get('bodyParts',[])]
            if any(b in injuries for b in bodyparts):
                contraindicated = True
            # check equipment availability
            item_eqs = [e.lower() for e in found_exact.get('equipments',[])]
            if not allowed_all and not any(e in allowed for e in item_eqs):
                unavailable = True
            else:
                unavailable = False
        else:
            # unknown exact exercise, use muscle mapping to decide contraindication
            contraindicated = False
            unavailable = False

        if contraindicated or unavailable:
            # Try to find a substitute that targets the same muscle or bodypart and is allowed
            substitute = None
            for item in db:
                item_body = [b.lower() for b in item.get('bodyParts',[])]
                item_target = [t.lower() for t in item.get('targetMuscles',[])]
                # match by muscle group or body part
                match_muscle = False
                if mg and (mg in item_body or mg in item_target):
                    match_muscle = True
                # skip exercises that hit injured body parts
                if any(b in injuries for b in item_body):
                    continue
                item_eqs = [e.lower() for e in item.get('equipments',[])]
                if not allowed_all and not any(e in allowed for e in item_eqs):
                    continue
                if match_muscle:
                    substitute = item
                    break

            if substitute:
                name = substitute.get('name')
                new_preds[name] = v.copy()
            else:
                # No substitute: reduce volume/intensity as a conservative fallback
                v2 = v.copy()
                v2['sets'] = max(1, int(round(v2['sets'] * 0.7)))
                v2['intensity'] = max(1, int(round(v2['intensity'] * 0.7)))
                new_preds[ex] = v2
        else:
            new_preds[ex] = v

    return new_preds
