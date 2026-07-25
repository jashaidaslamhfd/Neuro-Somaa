"""Créneaux indicatifs pour une audience France / francophonie.
Les données Analytics de la chaîne priment toujours sur ces horaires de départ.
"""
from datetime import datetime, timedelta
import pytz
class FrancePeakTimeScheduler:
    PEAK_TIMES=[{"hour":16,"minute":0,"name":"Après-midi"},{"hour":18,"minute":30,"name":"Fin de journée"},{"hour":21,"minute":0,"name":"Soirée"}]
    # DATA-DRIVEN (2026-07-25 autopsy): every 1k+ winner published 16:00-21:48
    # Paris; the 07:30/12:30 slots produced all the flops. Morning slot killed.
    def __init__(self): self.paris_tz=pytz.timezone("Europe/Paris"); self.utc_tz=pytz.UTC
    def get_next_posting_times(self,count=3):
        now=datetime.now(self.paris_tz); result=[]
        for day in range(3):
            for slot in self.PEAK_TIMES:
                when=self.paris_tz.localize(datetime.combine((now+timedelta(days=day)).date(),datetime.min.time()).replace(hour=slot['hour'],minute=slot['minute']))
                if when>now: result.append({"time_paris":when.strftime('%Y-%m-%d %H:%M %Z'),"time_utc":when.astimezone(self.utc_tz).isoformat(),"peak_name":slot['name'],"reason":"Créneau de consultation France / francophonie"})
        return result[:count]
    def get_scheduled_publish_settings(self,posting_time):
        return {"publishAt":posting_time.astimezone(self.utc_tz).isoformat(),"privacyStatus":"private","timezone":"Europe/Paris","localTime":posting_time.astimezone(self.paris_tz).strftime('%Y-%m-%d %H:%M:%S')}
    def validate_posting_interval(self,last_post_time): return (datetime.now(pytz.UTC)-last_post_time.astimezone(pytz.UTC)).total_seconds()>=7200
USAPeakTimeScheduler=FrancePeakTimeScheduler
