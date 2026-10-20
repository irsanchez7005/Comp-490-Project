from datetime import datetime,date,timedelta
#we generate slots based on their input for day of choice, start time, end time, gap time, and slot duration
def generate_slots(
        start_time,
        end_time,
        slot_duration,
        gap_duration=0
):
    if slot_duration <=0 or gap_duration <0:
        raise ValueError("Invalid time slot or gap duration")
    
    slots=[]

    current = datetime.combine(date.today(),start_time)
    end = datetime.combine(date.today(),end_time)
    duration = timedelta(minutes=slot_duration)
    gap=timedelta(minutes=gap_duration)

    #make sure time slot doesn't go over end time
    while current + duration <= end:
        slot_end=current + duration
        slots.append({"start": current.time(), "end": slot_end.time()})

        #update the current slot with the gap time so next slot can be generated
        current = slot_end + gap
    return slots
