from utilities.choices import ChoiceSet


class NumberStatusChoices(ChoiceSet):
    key = 'TelephoneNumber.status'

    STATUS_AVAILABLE = 'available'
    STATUS_RESERVED = 'reserved'
    STATUS_ASSIGNED = 'assigned'
    STATUS_PORTING = 'porting'
    STATUS_DEPRECATED = 'deprecated'

    CHOICES = [
        (STATUS_AVAILABLE, 'Available', 'green'),
        (STATUS_RESERVED, 'Reserved', 'cyan'),
        (STATUS_ASSIGNED, 'Assigned', 'blue'),
        (STATUS_PORTING, 'Porting', 'orange'),
        (STATUS_DEPRECATED, 'Deprecated', 'red'),
    ]
