from app.utils.confidence import weighted_confidence

def ensemble(t_text, t_conf, e_text, e_conf):

    conf = weighted_confidence(t_conf, e_conf)

    text = t_text if t_conf >= e_conf else e_text

    return text, conf
