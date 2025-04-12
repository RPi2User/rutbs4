# REST-API Sequences

## Backend Startup

```mermaid
sequenceDiagram
```

## Host Functions

```mermaid
sequenceDiagram

actor Caller
participant Backend
participant td as TapeDrive
participant Host
participant toc as TableOfContent
participant System


rect rgba(128,128,128,0.1)
note over Caller,Backend: Fetches the root endpoint of the backend

activate Caller
    Caller ->> Backend: GET: {/}
    activate Backend
        Backend ->> Caller: 200: 'THIS IS A RUTBS BACKEND'
    deactivate Backend
deactivate Caller

end

rect rgba(128,128,128,0.1)
note over Caller,Backend: Get a simple 200 response from Node

activate Caller
    Caller ->> Backend: GET: {/host}
    activate Backend
        Backend ->> Caller: 200: {}
    deactivate Backend
deactivate Caller

end

rect rgba(128,128,128,0.1)
note over Caller,Backend: Debugging path triggered

activate Caller
    Caller ->> Backend: GET: {/host/debug}
    activate Backend
    Backend ->> Backend: DEBUG?
    Backend -->> Caller: 418: {}
    note over Backend, System: THIS IS A DEBUG-PATH!
    Backend ->> System: print: "DEBUG done"
    Backend ->> Caller: 418: {}
    deactivate Backend
deactivate Caller

end

rect rgba(128,128,128,0.1)
note over Caller,Backend: Fetches the version of the backend service

activate Caller
    Caller ->> Backend: GET: {/host/version}
    activate Backend
        Backend ->> Caller: 200: JSON {"version": VERSION}
    deactivate Backend
deactivate Caller

end

rect rgba(128,128,128,0.1)
note over Caller,Backend: Fetches status of this node

activate Caller
    Caller ->> Backend: GET: {/host/status}
    activate Backend
        Backend ->> Host: getHostStatus()
        activate Host
            Host ->> Host: refreshStatus()

            Host ->> System: Hostname?
            activate System
                System ->> Host: {Hostname}

            deactivate System
                Host ->> System: IPv4-Adress?
            activate System
                System ->> Host: {IPv4-Adress}
            deactivate System
            
                Host ->> System: Uptime?
            activate System
                System ->> Host: {uptime in sec.}
            deactivate System
            
                Host ->> System: CPU-Utilization?
            activate System
                System ->> Host: {cpu-usage{,}}
            deactivate System

                Host ->> System: Memory-Allocation?
            activate System
                System ->> Host: {memory{,}}

            deactivate System
                Host ->> System: System-Load?
            activate System
                System ->> Host: {load{,}}                
            deactivate System
            
            Host ->> Backend: JSON{…} 
        deactivate Host
        Backend ->> Caller: 200: JSON{…}
    deactivate Backend
deactivate Caller

end




```

## Tape-Drive Functions

```mermaid
sequenceDiagram


rect rgba(128,128,128,0.1)
note over Caller,System: Rewinds the tape drive to the beginning

activate Caller
Caller ->> Backend: "POST /drive/<alias>/rewind"
    activate Backend
        Backend ->> td: tapeDrive.rewind()
    deactivate Backend
deactivate Caller
end

note over Caller,System: Ejecting


```
