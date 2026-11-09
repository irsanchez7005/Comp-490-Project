from datetime import datetime,date,timedelta
from .models import TimeSlot
from facility.models import FacilitySchedule,FacilityPricing,TimeSlot
#we generate slots based on their input for day of choice, start time, end time, gap time, and slot duration
def generate_slots(
        start_time,
        end_time,
        slot_duration,
        gap_duration=0,
        slot_interval=15
):
    if slot_duration <=0 or gap_duration <0:
        raise ValueError("Invalid time slot or gap duration")
    
    slots=[]

    current = datetime.combine(date.today(),start_time)
    end = datetime.combine(date.today(),end_time)
    duration = timedelta(minutes=slot_duration)
    interval= timedelta(minutes=slot_interval)
    gap=timedelta(minutes=gap_duration)

    if slot_duration <= 0 or slot_interval <= 0:
        raise ValueError("Duration and interval must be postive")

    #make sure time slot doesn't go over end time
    while current + duration <= end:
        slot_end=current + duration
        slots.append({"start": current.time(), "end": slot_end.time()})

        #update the current slot with the gap time so next slot can be generated
        current += interval
    return slots

def create_facility_timeslots(
        facility,
        selected_date
):
    schedules = FacilitySchedule.objects.filter(facility=facility,day_of_week=selected_date.weekday())
    pricing_rules= list(FacilityPricing.objects.filter(facility=facility,day_of_week=selected_date.weekday()))
    created_slots=[]
    """This function creates timeslots for facilities, so calendar can pull all timeslots from database, facilities can create a schedule by selecting day,time, and duration"""
    """First we get start time for each schedule, then get details of each, also checks if timeslot already exists"""
    for schedule in schedules:

        generated_times= generate_slots(schedule.start_time,schedule.end_time,schedule.slot_duration,schedule.gap_duration,schedule.slot_interval)

        for generated in generated_times:
            start = generated["start"]

            matching_rules=[
                rule for rule in pricing_rules
                if rule.start_time <= start < rule.end_time
            ]
            """Not allowing missing pricing"""
            if len(matching_rules) !=1:
                continue
            slot, created = TimeSlot.objects.get_or_create(facility=facility,date=selected_date,start_time=start,
                                            defaults={ "price_per_player": matching_rules[0].price_per_player, "max_players": 4,},
                                                               )


            if created:
                created_slots.append(slot)   
    return created_slots
