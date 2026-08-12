"""Step 3 — the two halves of "something has to call it".

    monstertix/server.py    THE TRIGGER    an endpoint that can run the agent
    monstertix/clock.py     THE TRIGGERER  something with a clock that calls it

They are two files on purpose. In production they are two machines: the trigger
becomes Cloud Run, the triggerer becomes Cloud Scheduler. Collapsing them into
one script hides the only interesting thing about the arrangement — that the
half with the clock knows nothing about agents, and the half with the agent
knows nothing about time.
"""
