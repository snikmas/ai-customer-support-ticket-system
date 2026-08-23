# Permission matrix

| Area | User | Agent | Read-only agent | Manager | Admin | Super Admin |
| --- | --- | --- | --- | --- | --- | --- |
| Own tickets/comments | own | assigned/new queue | visible tickets | all active | all active | all active |
| Ticket assignment/routing | no | claim own queue | no | yes | yes | yes |
| Ticket customer summary | own ticket | assigned ticket | no | yes | yes | yes |
| Related links | no | assigned ticket | no | yes | yes | yes |
| User directory | no | no | no | read | read/write | read/write |
| Staff creation / role changes | no | no | no | no | yes | yes |
| Departments and skills | active reads used by workflow | active reads | active reads | manage | manage | manage |
| Personal profile/password | self | self | self | self | self | self |
| Agent availability | no | self | no | self | self | self |
| Notifications | recipient only | recipient only | recipient only | recipient only | recipient only | recipient only |
| Global AI settings and provider tests | no | no | no | no | yes | yes |

Authorization is applied before pagination for ticket and user directory
queries. A user response never includes password or refresh-session fields.
The last active Super Admin and an administrator's final administrative access
are protected by domain conflicts.
