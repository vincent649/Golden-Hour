"""Bystander first-aid guidance (English, Hindi, Bengali).

These are conservative, widely taught basics. The text has NOT been reviewed by a
clinician: have a doctor or first-aid trainer review and adapt it (ideally against the
official Indian first-aid guidelines) before any real-world use.
"""

LANGS = {"en": "English", "hi": "हिन्दी", "bn": "বাংলা"}

_STEPS = {
    "en": [
        ("Stay safe", "Check your own safety first. Keep away from moving traffic and ask people nearby to help."),
        ("Call 112", "The app has already alerted responders. If you can, also call 112 and give the location."),
        ("Do not move the person", "Do not move them unless there is danger such as fire or oncoming vehicles. They may have a neck or spine injury."),
        ("Stop heavy bleeding", "Press firmly on the wound with a clean cloth. Do not pull out anything stuck in the wound."),
        ("Leave the helmet on", "Do not remove a helmet. Do not give food or water."),
        ("Check breathing", "If the person is unconscious and not breathing normally, tell the 112 operator and follow their instructions. Give CPR only if you are trained."),
        ("Stay with them", "Stay, keep talking to them and keep them calm until the ambulance arrives."),
    ],
    "hi": [
        ("सुरक्षित रहें", "पहले अपनी सुरक्षा देखें। चलते ट्रैफिक से दूर रहें और आसपास के लोगों से मदद माँगें।"),
        ("112 पर कॉल करें", "ऐप ने मदद के लिए अलर्ट भेज दिया है। हो सके तो 112 पर भी कॉल करें और जगह बताएँ।"),
        ("घायल को न हिलाएँ", "आग या सामने से आते वाहनों जैसा ख़तरा न हो तो घायल को न हिलाएँ। गर्दन या रीढ़ में चोट हो सकती है।"),
        ("ज़्यादा खून रोकें", "साफ़ कपड़े से घाव को मज़बूती से दबाएँ। घाव में फँसी किसी चीज़ को न निकालें।"),
        ("हेलमेट न उतारें", "हेलमेट न उतारें। घायल को खाना या पानी न दें।"),
        ("साँस देखें", "अगर व्यक्ति बेहोश है और सामान्य रूप से साँस नहीं ले रहा, तो 112 ऑपरेटर को बताएँ और उनके निर्देश मानें। प्रशिक्षित हों तभी सीपीआर दें।"),
        ("साथ रहें", "एम्बुलेंस आने तक व्यक्ति के साथ रहें, उससे बात करते रहें और उसे शांत रखें।"),
    ],
    "bn": [
        ("নিজের নিরাপত্তা দেখুন", "আগে নিজের নিরাপত্তা নিশ্চিত করুন। চলন্ত গাড়ি থেকে দূরে থাকুন এবং আশেপাশের মানুষের সাহায্য নিন।"),
        ("১১২ নম্বরে ফোন করুন", "অ্যাপ সাহায্যের জন্য সতর্কবার্তা পাঠিয়েছে। সম্ভব হলে ১১২ নম্বরেও ফোন করে জায়গার কথা জানান।"),
        ("আহত ব্যক্তিকে নড়াবেন না", "আগুন বা ধেয়ে আসা গাড়ির মতো বিপদ না থাকলে আহত ব্যক্তিকে নড়াবেন না। ঘাড় বা মেরুদণ্ডে আঘাত থাকতে পারে।"),
        ("রক্তপাত থামান", "পরিষ্কার কাপড় দিয়ে ক্ষতস্থানে জোরে চেপে ধরুন। ক্ষতে আটকে থাকা কিছু টেনে বের করবেন না।"),
        ("হেলমেট খুলবেন না", "হেলমেট খুলবেন না। আহত ব্যক্তিকে খাবার বা জল দেবেন না।"),
        ("শ্বাস দেখুন", "ব্যক্তি অচেতন হলে এবং স্বাভাবিকভাবে শ্বাস না নিলে ১১২-এর অপারেটরকে জানান এবং তাঁদের নির্দেশ মানুন। প্রশিক্ষিত হলে তবেই সিপিআর দিন।"),
        ("পাশে থাকুন", "অ্যাম্বুলেন্স না আসা পর্যন্ত আহত ব্যক্তির পাশে থাকুন, কথা বলতে থাকুন এবং তাঁকে শান্ত রাখুন।"),
    ],
}

_LEGAL = {
    "en": "Good Samaritan protection: under Indian law and guidelines, a person who helps an accident victim should not face legal harassment. You do not have to give your name or personal details.",
    "hi": "गुड सामरिटन सुरक्षा: भारतीय कानून और दिशानिर्देशों के अनुसार दुर्घटना में मदद करने वाले को कानूनी परेशानी नहीं होनी चाहिए। अपना नाम या निजी जानकारी देना ज़रूरी नहीं है।",
    "bn": "গুড সামারিটান সুরক্ষা: ভারতীয় আইন ও নির্দেশিকা অনুযায়ী দুর্ঘটনায় সাহায্যকারীকে আইনি হয়রানি করা উচিত নয়। নিজের নাম বা ব্যক্তিগত তথ্য দিতে আপনি বাধ্য নন।",
}

_DISCLAIMER = {
    "en": "This is general guidance, not a substitute for a trained paramedic or doctor.",
    "hi": "यह सामान्य मार्गदर्शन है, प्रशिक्षित पैरामेडिक या डॉक्टर का विकल्प नहीं।",
    "bn": "এটি সাধারণ নির্দেশনা, প্রশিক্ষিত প্যারামেডিক বা চিকিৎসকের বিকল্প নয়।",
}


def get_guidance(lang: str) -> dict:
    if lang not in _STEPS:
        lang = "en"
    return {
        "lang": lang,
        "languages": LANGS,
        "steps": [{"n": i + 1, "title": t, "text": x} for i, (t, x) in enumerate(_STEPS[lang])],
        "legal": _LEGAL[lang],
        "disclaimer": _DISCLAIMER[lang],
        "clinically_reviewed": False,
    }
