The Job Scheduling System should be a simple batch job system.
A Process can Schedule a Job just by providing the Command Object.
Each Job will get wrapped automagically.
When the first Job gets queried the Scheduler will start the worker thread.

## ThreadLimit := 1

Job works on "First Come, First Serve" unless a Childprocess can be started.

## Typical flow with 4 concurrent tasks and 2 threads

This shows how the Scheduler handles dependencies. As you can see only two tasks are running simultaneously.

1. A and C
2. B and C
3. B and D
4. only D

Note: The worker thread from Job will always run and does not count as running task.

```mermaid
sequenceDiagram
Note over Caller, Job: ThreadLimit:=2

Caller->>Job: Schedules Task A
Job ->> Caller: A.uuid
Caller->>Job: Schedules Task B depends on A
Job ->> Caller: B.uuid
Caller->>Job: Schedules Task C
Job ->> Caller: C.uuid
Caller->>Job: Schedules Task D
Job ->> Caller: D.uuid

create Participant A
Job->>A: state = QUEUED
create Participant B
Job->>B: state = WAIT_FOR_PARENT
create Participant C
Job->>C: state = QUEUED
create Participant D
Job ->>D: state = QUEUED

Caller->>Job: Work()
activate Job
Note over Job,A: A came first will be executed first
Job->>A: state?
A ->> Job: QUEUED
Job->>A: Run()
activate A
    A->>A: state:= RUNNING
    A->>A: works...
    Note over Job,B: Job seeks for next Entry
    Job->>B: state?
    B ->> Job: WAIT_FOR_PARENT
    Job->>B: parent?
    B ->> Job: uuid(A)
    Job ->> A: state?
    A ->> Job: RUNNING
    Note over Job,B: B cannot be scheduled, proceeds with C
    Job ->> C: state?
    C ->> Job: QUEUED
    Job ->> C: Run()
    activate C
    C->>C: works...

    Note over Job,C: Since all threads are currently working, Job is done.
    Job->>Job: Tick: Refresh()
    Note over Job,A: A finishes its task
    A->>A: finished
    A->>A: state := COMPLETED
deactivate A
Job->>Job: Tick: Refresh()
Job->>A: state?
A->>Job: COMPLETED
Job->>B: state?
B->>Job: WAIT_FOR_PARAENT
Job->>B: parent?
B->>Job: uuid(A)
Job ->> A: state?
A ->> Job: COMPLETED

Job->>B: Run()
activate B
B->>B: state:=RUNNING
B->>B: works...

Job->>Job: Tick: Refresh()
Note over Job,C: C finishes execution
C ->> C: finished
C ->> C: state := COMPLETED
deactivate C

Job->>Job: Tick: Refresh()
Note over Job,D: Job seeks for next Entry
Job ->> A: state?
A ->> Job: COMPLETED

Job ->> B: state?
B ->> Job: RUNNING

Job ->> C: state?
C ->> Job: COMPLETED

Job ->> D: state?
D ->> Job: QUEUED
note over Job,D: Note: This is the first time D get asked

Job ->> D: Run()
activate D

D ->> D: works...

Note over Job,D: Wait for any task to complete

Job->>Job: Tick: Refresh()


B ->> B: finished
B ->> B: state := COMPLETED
deactivate B

Job->>Job: Tick: Refresh()
Note over Job,D: Job asks A,B,C,D for their state<br> but no additional Entry is queried

D ->> D: finished
D ->> D: state := COMPLETED

deactivate D
Job ->> Job: Tick: Refresh()
deactivate Job
```

Priorities:

The Scheduler is sensible to INTERNAL priorities.


OOOE (OutOfOrderExecution)
In order to prevent a critical Job from dangling "somewhere" in the Queue. All Jobs can promoted to an "URGENT" Job.
But the Command Timeout will be set to 100ms. After that the process will be terminated forcefully.

This project has implemented a flexible Framework to issue Commands (`class Command`) on the host system.
Command has no scheduling capabilities. 
When the System calls a Command to be executed this Scheduler (`Job`) wraps it around a `Entry`-Object.

A Job contains the following:

```mermaid
classDiagram

class Entry{
+ command: Command
+ id: str→uuid
+ dependsOn: str→uuid = ""
+ state: EntryState = QUEUED
}

class Job{
- DEFAULT_THREADLIMIT: int >= 1 
- limit: int = DEFAULT_THREADLIMIT
- queue: List[Entry]
+ Add(_cmd: Command) str→uuid
+ Get(uuid: str) dict 
+ Registry(None) dict[queue]
+ Flush(killAllRunning: bool = True) None
}

```
